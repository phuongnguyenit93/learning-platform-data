# `equals` and `hashCode` of source keys in Spring for GraphQL

With `@BatchMapping`, Spring for GraphQL groups multiple parent sources into a single batch. If the batch method returns `Map<S, T>`, each key in the map is a source object and its value is the resolved field result for that source. Because Java's `Map` looks up keys based on `equals()` and `hashCode()`, these two methods determine whether Spring matches each result back to the right parent source.

This detail often goes unnoticed when using Java records or when the map retains the exact original object instances. However, if a batch loader constructs new objects, uses JPA entities/proxies, or has mutable source state, two objects representing the same record may not be considered equal. The field can then receive `null` even though the batch loader successfully loaded the data.

## 1. What is a source key in `@BatchMapping`?

Suppose the schema has a list of books and a `Book.author` field:

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

When a client queries:

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

The `Query.books` resolver returns multiple `Book`s. Instead of calling the author service separately for each book, `@BatchMapping` receives the entire list of sources and loads authors in bulk:

```java
@BatchMapping(typeName = "Book", field = "author")
Mono<Map<Book, Author>> authors(List<Book> books) {
    // Load authors by authorId for all books.
}
```

With the `Map<Book, Author>` return type:

- The `Book` key identifies the parent source to which the result belongs.
- The `Author` value is the value for that source's `Book.author` field.
- When GraphQL completes the field for each source, results are matched by the corresponding key.

Example result map:

```java
Map<Book, Author> result = new HashMap<>();
result.put(bookA, authorA);
result.put(bookB, authorB);
```

Spring needs to locate the exact value corresponding to the source being resolved. Key lookup in a `HashMap` follows Java's `equals()` and `hashCode()` contract.

## 2. Why do `equals()` and `hashCode()` matter?

`HashMap` does not compare keys by inspecting arbitrary business fields. It uses `hashCode()` to locate the bucket, and then uses `equals()` to determine whether keys are equivalent.

Java's fundamental contract:

1. If `a.equals(b)` is `true`, then `a.hashCode()` and `b.hashCode()` must be equal.
2. Two objects with the same `hashCode()` are not necessarily equal; hash collisions are permitted.
3. `equals()` must be reflexive, symmetric, transitive, and consistent.
4. While an object is being used as a key in a hash-based map, the data participating in `equals()` and `hashCode()` must remain stable.

Example:

```java
BookSource sourceA = new BookSource(10L, 100L);
BookSource sourceB = new BookSource(10L, 100L);

Map<BookSource, Author> authors = new HashMap<>();
authors.put(sourceA, new Author(100L, "An Nguyen"));

Author result = authors.get(sourceB);
```

If `BookSource` implements equality based on its corresponding data, `result` can be the stored author even though `sourceA` and `sourceB` are two different object instances. If the class only uses the default `Object.equals()`, two distinct instances are not equal and `result` is `null`.

## 3. Identity equality vs. value equality

By default, a Java class that does not override `equals()` and `hashCode()` inherits behavior from `Object`:

- `equals()` returns `true` only when two variables reference the exact same object instance.
- `hashCode()` is tied to object identity throughout the appropriate lifetime of the instance.

This is **identity equality**. Two distinct object instances representing the same database record are still not equal.

**Value equality** considers two objects equal if the chosen identifying values are equal. Java records automatically generate `equals()` and `hashCode()` based on the record components:

```java
public record BookSource(Long id, Long authorId) {}

BookSource first = new BookSource(1L, 10L);
BookSource second = new BookSource(1L, 10L);

System.out.println(first.equals(second)); // true
System.out.println(first.hashCode() == second.hashCode()); // true
```

Two distinct record instances with identical components will be equal. This is helpful when a batch loader constructs an equivalent source object instead of reusing the exact original instance.

However, a record is only right if its components are appropriate for defining equality. If fields change frequently or contain complex associations, auto-generated equality may be unsuitable as a source key. Choose keys based on stable business identity, not merely on whether a class is a record.

## 4. `@BatchMapping` example using source as key

Suppose the models are immutable records:

```java
public record Book(Long id, String title, Long authorId) {}

public record Author(Long id, String name) {}
```

Service loading authors by a set of IDs:

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

Batch mapping:

```java
@Controller
class BookController {

    private final BookService bookService;
    private final AuthorService authorService;

    BookController(BookService bookService, AuthorService authorService) {
        this.bookService = bookService;
        this.authorService = authorService;
    }

    @QueryMapping
    List<Book> books() {
        return bookService.findAll();
    }

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
}
```

Here the map uses the exact `Book` objects received from the source list as keys. Because Java records implement `equals()` and `hashCode()`, the map can also match by value equality if the framework or batch loader uses another instance with identical components.

If an author is not found, the example omits the corresponding key from the map. That causes the `author` field to have no result and resolve as `null`. Since the schema declares `author: Author` as nullable, this case is valid. If the schema were `author: Author!`, a missing value would violate non-nullability and could trigger null propagation.

## 5. Failure when source class does not override equality

Consider a regular class:

```java
public class BookSource {

    private final Long id;
    private final Long authorId;

    public BookSource(Long id, Long authorId) {
        this.id = id;
        this.authorId = authorId;
    }

    public Long id() {
        return id;
    }

    public Long authorId() {
        return authorId;
    }
}
```

This class does not override `equals()` and `hashCode()`. The following two instances represent the same data yet are not equal:

```java
BookSource sourceFromQuery = new BookSource(1L, 10L);
BookSource sourceFromBatch = new BookSource(1L, 10L);

Map<BookSource, Author> result = new HashMap<>();
result.put(sourceFromBatch, new Author(10L, "An Nguyen"));

Author author = result.get(sourceFromQuery); // null
```

`HashMap` searches using `sourceFromQuery`, whereas the stored key is `sourceFromBatch`. Because the two objects do not share identity and the class lacks value equality, the map fails to find the entry.

This can happen when code constructs a new object as the key instead of using the exact source received. Check where keys are constructed in the batch method, not only whether the internal data looks the same.

If the map always uses the exact source instances received from the `List<S>` parameter, identity equality may suffice for that map alone. However, do not rely implicitly on this detail if code might copy, reconstruct, or transform source objects in subsequent steps.

## 6. Implementing equality by business identity

For regular DTO classes, you can implement equality based on a stable identifier. For example, `BookSource` is an immutable DTO where `id` identifies a source:

```java
public final class BookSource {

    private final Long id;
    private final Long authorId;

    public BookSource(Long id, Long authorId) {
        this.id = id;
        this.authorId = authorId;
    }

    public Long id() {
        return id;
    }

    public Long authorId() {
        return authorId;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof BookSource that)) {
            return false;
        }
        return Objects.equals(id, that.id);
    }

    @Override
    public int hashCode() {
        return Objects.hash(id);
    }
}
```

In this example, two sources with the same `id` are considered the same logical entity. `authorId` does not participate in equality because it is relational data rather than the source's identifier.

Only choose `id` for equality when the ID is truly stable and unique within the application's scope. If sources can be transient objects without IDs yet, multiple objects with `id == null` might accidentally be treated as equal. Explicitly decide how to handle unpersisted entities, or use a DTO with another stable key.

## 7. Common equality pitfalls with JPA entities

JPA entities are typically mutable classes with a persistence lifecycle and can be wrapped by Hibernate proxies. Therefore, do not apply a single generic `equals()`/`hashCode()` template to every entity.

### Using all fields in `equals()` and `hashCode()`

Some code generators create equality based on every field. With entities, this easily causes problems:

- Mutable fields change after the entity has been placed in a `HashMap`.
- Lazy associations can be triggered unintentionally just for equality checks.
- Bidirectional relationships can cause infinite recursion during equality or hash computation.
- Two entities with the same ID but different field states can be considered unequal.

Therefore, avoid using Lombok's `@Data` by default on JPA entities that have associations. If you use Lombok, explicitly configure which fields participate in `equals()` and `hashCode()`, or implement them manually according to your project's entity guidelines.

### Using generated IDs carelessly

If an ID is generated only upon persistence, two new entities have `id == null`. An implementation that only compares IDs may treat all unsaved entities as equal. The hash code can also change when an ID is assigned after the object has already been used as a map key.

For JPA entities, choose a proven equality strategy for the ORM in use, accounting for transient entities, persistent entities, and proxies. Some projects use a unique immutable natural key; others use the persistent ID with special handling for transient instances.

### Ignoring proxies

A Hibernate proxy can be a subclass or wrapper of an entity. Checking `getClass()` directly inside `equals()` can prevent a real entity and a proxy of the same entity from being considered equal. Exact class/proxy handling depends on the ORM and version; follow your project's entity equality convention rather than writing a quick implementation without checking proxy behavior.

With GraphQL, a clean option is often converting entities into immutable DTOs/records before exposing them to the schema. DTOs can have clear equality, never trigger lazy loading, and do not expose persistence-layer lifecycle details.

## 8. Do not let keys mutate after inserting into a Map

A key used in a `HashMap` must keep the fields participating in `equals()` and `hashCode()` unchanged while stored in the map.

Unsafe example:

```java
class MutableBookKey {
    private Long id;

    // both equals() and hashCode() rely on id
}

MutableBookKey key = new MutableBookKey();
Map<MutableBookKey, Author> map = new HashMap<>();
map.put(key, author);

key.setId(10L); // hashCode may change after insertion

Author found = map.get(key); // entry may not be found
```

When the hash code changes, the entry remains in the old bucket while lookup computes a new bucket. As a result, `get(key)` can return `null` even though the map still contains the entry.

For source keys in `@BatchMapping`, prefer immutable objects or equality based on an immutable identifier. Never mutate fields participating in equality after the source has been used as a key.

## 9. Source equality must reflect field semantics

Just because two objects share an ID does not always mean they are interchangeable for every field. Equality must match the meaning of the source in the schema.

For instance, if `Book.author` depends only on `bookId`, equality by `id` may be reasonable. However, if the field's result also depends on the source's version, tenant, locale, or state, equality based solely on ID can collapse two differently scoped sources into a single key.

DataLoader can also use key equality to cache and deduplicate `load()` calls. If two sources are considered equal when they actually require different results, one result may be incorrectly reused for both.

When a source has multiple identifying dimensions, consider:

- Using a source DTO whose equality reflects the exact required context.
- Using an immutable composite key containing all components that determine the result.
- Switching to a DataLoader method argument with an explicit key like `DataLoader<BookKey, Author>` or `DataLoader<Long, Author>` if you want to decouple the source object from the data-loading key.

Do not include every field in `equals()` just to avoid key collisions. Define precisely when two sources can share the same batched field result.

## 10. Alternative: returning a List in exact source order

With `@BatchMapping`, you can return a result list in the exact order of the source list instead of `Map<S, T>`:

```java
@BatchMapping(typeName = "Book", field = "author")
Mono<List<Author>> authors(List<Book> books) {
    List<Long> authorIds = books.stream()
        .map(Book::authorId)
        .toList();

    return authorService.findAuthorsInOrder(authorIds)
        .collectList();
}
```

With a positional list, the first result element must correspond to the first source, the second to the second source, and so on. Count and order must strictly follow the batch mapping contract. This avoids requiring the source object to serve as a `Map` key, though the service must guarantee ordering and how missing elements are represented.

If some relationships may be absent, place `null` at the exact index only when the GraphQL field is nullable and the collection type used allows null elements. If ordering cannot be guaranteed, `Map<S, T>` is usually easier to control, provided source equality is properly designed.

## 11. When should you use DataLoader with an ID instead of a source key?

If you want to avoid relying on entity/source object equality, you can use a DataLoader method argument keyed by an ID or an immutable key value object.

Registering an ID-keyed loader:

```java
registry.forTypePair(Long.class, Author.class)
    .registerMappedBatchLoader((authorIds, environment) ->
        authorService.findAllByIds(authorIds)
            .collectMap(Author::id)
    );
```

Resolver:

```java
@SchemaMapping(typeName = "Book", field = "author")
CompletableFuture<Author> author(
        Book book,
        DataLoader<Long, Author> authorLoader) {

    return authorLoader.load(book.authorId());
}
```

Here the DataLoader key is `Long`, not `Book`. Key equality for loading data is `Long` equality, which is already stable. The source is still used to obtain `authorId`, without needing the source object itself as the key of the result map.

In return, this approach requires declaring `BatchLoaderRegistry` and an explicit DataLoader method argument. When source DTOs already have clean equality, `@BatchMapping` returning `Map<S,T>` is usually more concise.

## 12. Testing `equals()` and `hashCode()`

Before testing the full GraphQL query, verify the source type's equality with unit tests:

```java
class BookSourceEqualityTests {

    @Test
    void equalSourcesHaveSameHashCode() {
        BookSource first = new BookSource(1L, 10L);
        BookSource second = new BookSource(1L, 10L);

        assertThat(first).isEqualTo(second);
        assertThat(first.hashCode()).isEqualTo(second.hashCode());
    }

    @Test
    void mapCanFindEntryByEquivalentSource() {
        BookSource sourceFromQuery = new BookSource(1L, 10L);
        BookSource sourceFromBatch = new BookSource(1L, 10L);
        Author author = new Author(10L, "An Nguyen");

        Map<BookSource, Author> result = new HashMap<>();
        result.put(sourceFromBatch, author);

        assertThat(result.get(sourceFromQuery)).isEqualTo(author);
    }
}
```

This unit test proves two equivalent instances can be used interchangeably as map keys. For JPA entities, add tests covering transient entities, persisted entities, proxies, and state after ID assignment per your project's equality strategy.

## 13. Integration testing `@BatchMapping`

In addition to equality unit tests, test the GraphQL response to ensure each source receives the right batch result:

```java
@GraphQlTest(BookController.class)
class BookBatchMappingTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @MockitoBean
    AuthorService authorService;

    @Test
    void mapsAuthorsToTheirBookSources() {
        given(bookService.findAll()).willReturn(List.of(
            new Book(1L, "Book A", 10L),
            new Book(2L, "Book B", 20L)
        ));

        given(authorService.findAllByIds(Set.of(10L, 20L)))
            .willReturn(Flux.just(
                new Author(10L, "Author A"),
                new Author(20L, "Author B")
            ));

        GraphQlTester.Response response = graphQlTester.document("""
                query {
                    books {
                        title
                        author {
                            name
                        }
                    }
                }
                """)
            .execute();

        response.path("books[0].author.name")
            .entity(String.class).isEqualTo("Author A");
        response.path("books[1].author.name")
            .entity(String.class).isEqualTo("Author B");
    }
}
```

This is an illustrative example; imports, static import `given`, models, services, and SDL must be present in the test context. Depending on the Spring Boot version, the mock bean annotation may be `@MockitoBean` or `@MockBean`. Add tests with sources reconstructed into separate instances sharing the same identifier to verify equality behaves properly in your application's map-building logic.

## 14. Common mistakes

**Assuming the same ID means the same object.** If a class uses `Object`'s default equality, two distinct instances are not equal even if they share the same ID. Check `equals()` and `hashCode()`.

**Overriding `equals()` while forgetting `hashCode()`.** Two equal objects can produce different hashes, preventing `HashMap` from locating the key. Always implement both using the same identifier.

**Using mutable fields in equality.** Modifying a field after insertion can change the hash code and make the entry unreachable. Prefer immutable keys.

**Including all associations of a JPA entity.** Equality can trigger lazy loading, cause cycles, or hurt performance. Pick a stable identifier and account for proxies.

**Using generated IDs on transient entities without handling `null`.** Multiple unsaved entities may be treated as equal. Design specifically for unpersisted states.

**Making equality overly broad.** Two sources with different contexts but the same ID may collapse onto one key, causing one result to be misapplied to another source. Equality must reflect the semantics of the batched field.

**Returning a map missing keys for a Non-null field.** When a value is absent, the field can become `null` and violate the schema. Choose appropriate nullability or error representation.

**Returning a List without preserving order.** When using positional results, each element must match the source at the same index. You cannot sort arbitrarily by database return order.

## Conclusion

When `@BatchMapping` returns `Map<S, T>`, the source object is the key used to match results to each parent. `HashMap` and many other map implementations rely on `hashCode()` followed by `equals()` to locate keys. Use immutable source DTOs/records whose equality accurately reflects business identity, avoid mutable keys, and handle JPA entities/proxies with care. If you do not want source objects serving as keys, consider an accurately ordered positional `List` or a DataLoader with an explicit ID/key value object. Test both equality in isolation and GraphQL responses to catch source-matching bugs early.

## References

- [Spring for GraphQL — Annotated Controllers: `@BatchMapping`](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Java Platform — `Object.equals` and `Object.hashCode`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html)
- [Java Platform — `Map`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html)
