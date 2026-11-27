# Collection Return Type

In GraphQL, a field can return a list of values. For example, a `books` field returns multiple books, `authors` returns a list of authors, or `tags` returns a list of strings. In the schema, a list is represented with square brackets; in Java, a resolver typically returns `List<T>` or an appropriate collection type. A **collection return type** is the way a collection of results from Java is mapped to a list-typed field in GraphQL.

With Spring for GraphQL, a controller method can return `List`, `Collection`, or an appropriate result type that GraphQL Java can handle as a list. Spring registers the method as a data fetcher; the GraphQL runtime uses the field type in SDL to validate, resolve each element, and build the response. Therefore, you need to design the list type in SDL, the Java collection type, nullability rules, and result ordering together.

## Declaring lists in GraphQL SDL

GraphQL uses square brackets to declare a list type:

~~~graphql
type Query {
  books: [Book]
  titles: [String]
  ratings: [Int]
}

type Book {
  id: ID!
  title: String!
}
~~~

`[Book]` means the `books` field returns a list of `Book`. Each element of the list can be null, and the list itself can also be null. Similarly, `[String]` is a list of strings and `[Int]` is a list of integers.

Lists can be nested:

~~~graphql
type Query {
  matrix: [[Int]]
}
~~~

The `matrix` field returns a list of lists of integers. Nested types can be useful for matrix-like data or grouping by date, but for business data, a named object type is usually easier to understand and extend than a deeply nested list structure.

## Combining lists with non-null

The exclamation mark can be applied to the list or to each element. Its position determines whether the list and its elements are allowed to be null:

| SDL type | Can the list be null? | Can an element be null? |
| --- | --- | --- |
| [Book] | Yes | Yes |
| [Book!] | Yes | No |
| [Book]! | No | Yes |
| [Book!]! | No | No |

Example:

~~~graphql
type Query {
  books: [Book!]!
}
~~~

With this declaration, the `books` field must return a non-null list and every element in the list must also be non-null. An empty list `[]` is still valid because a list can contain zero elements without being null.

Nullability is a GraphQL contract; it is not inferred automatically from the Java type `List<Book>`. If SDL declares `[Book!]!`, the resolver must provide a non-null collection containing no null elements. If the resolver returns null or includes a null element, GraphQL generates an execution error and applies null propagation rules up to the nearest nullable parent field.

For example, if an element is null in a `[Book!]!` list, the entire `books` field becomes null because the element is declared non-null; since the `books` field itself is also non-null, null continues propagating to the parent. If this field is directly on the `Query` root, the response may have `data: null`. Therefore, only use non-null when the application can genuinely guarantee that condition.

## Empty list and null are different

The following two results have different meanings:

~~~json
{
  "data": {
    "books": []
  }
}
~~~

An empty list means the query succeeded but no matching books were found.

~~~json
{
  "data": {
    "books": null
  }
}
~~~

A `null` value can represent a field with no value, a field that could not be resolved, or that an error occurred if the schema allows null at that position. For a list field when no records are found, you should normally return an empty collection instead of null.

In Java:

~~~java
return List.of();
~~~

returns an empty list. Meanwhile:

~~~java
return null;
~~~

returns null and can cause an error if SDL declares the field as non-null. Standardize the convention in the service so the controller does not have to guess the meaning of null.

## Using List in an annotated controller

Example schema:

~~~graphql
type Query {
  books: [Book!]!
}

type Book {
  id: ID!
  title: String!
  publishedYear: Int
}
~~~

Controller returning `List<Book>`:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }
}
~~~

The service can return a collection from a repository:

~~~java
public interface BookRepository extends JpaRepository<Book, String> {
}

@Service
public class BookService {

    private final BookRepository bookRepository;

    public BookService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    public List<Book> findAll() {
        return bookRepository.findAll();
    }
}
~~~

The GraphQL runtime receives the list and resolves each element according to the `Book` type. If the client only selects `id` and `title`, the runtime only needs to execute those fields in the selection set:

~~~graphql
query {
  books {
    id
    title
  }
}
~~~

The response has a list-of-objects structure:

~~~json
{
  "data": {
    "books": [
      {
        "id": "book-101",
        "title": "Spring in Action"
      },
      {
        "id": "book-102",
        "title": "GraphQL in Action"
      }
    ]
  }
}
~~~

The Java return type does not decide which fields the client can select. SDL and the selection set determine the response shape; the collection simply supplies the source objects for GraphQL to continue resolving.

## Collection, Iterable, and array

Java has several types for representing a collection:

| Java type | Characteristics | When to use as a GraphQL result |
| --- | --- | --- |
| List<T> | Ordered, allows duplicate elements | Common choice for list fields |
| Collection<T> | General interface of many collections | Suitable when the service does not need to commit to a specific list type |
| Set<T> | Disallows duplicates based on equals/hashCode | Only use when order is not needed or ordering rules are explicit |
| Iterable<T> | Allows iterating over elements | Can be used when the data source only provides iteration |
| T[] | Array with fixed size after creation | Can be used, though usually less flexible than List |

GraphQL Java handles list values from iterable structures such as `Iterable` and arrays. In Spring for GraphQL applications, `List<T>` is usually the most readable and predictable choice because it clearly represents an ordered list.

Do not return `Set<T>` just because the current repository uses a `Set`. `Set` does not guarantee ordering under its general contract; a query could return elements in different orders across runs or across implementations. If the API needs stable ordering, sort explicitly and return `List<T>`.

Example of converting a `Set` to an ordered `List`:

~~~java
public List<Book> findAllSorted() {
    return bookRepository.findAll().stream()
            .sorted(Comparator.comparing(Book::title))
            .toList();
}
~~~

On Java versions that do not yet support `Stream.toList()`, you can use `collect(Collectors.toList())`. Ordering should be defined in the repository or service so every client receives the same contract.

## Element ordering in the response

GraphQL preserves the element order returned by the data fetcher. If a resolver returns an ordered `List`, the response preserves that order. However, a database does not guarantee ordering if the query has no `ORDER BY`.

Example:

~~~java
public List<Book> findByPublishedYear() {
    return bookRepository.findAllByOrderByPublishedYearDesc();
}
~~~

If ordering is part of the API, explicitly document the default sort or accept a sort argument from the client. Do not rely on incidental database or `HashSet` ordering.

When the client needs to choose the ordering:

~~~graphql
enum BookSort {
  TITLE_ASC
  TITLE_DESC
  PUBLISHED_YEAR_DESC
}

type Query {
  books(sort: BookSort = TITLE_ASC): [Book!]!
}
~~~

The resolver can translate the enum into an allowed sort criterion:

~~~java
@QueryMapping
public List<Book> books(@Argument BookSort sort) {
    return bookService.findAll(sort);
}
~~~

Only map the enum to sort properties supported by the application. Never concatenate arbitrary field names from the client directly into SQL.

## Nested collections in object types

Lists do not only appear at the `Query` root. An object type can contain a field returning a collection:

~~~graphql
type Book {
  id: ID!
  title: String!
  reviews: [Review!]!
}

type Review {
  id: ID!
  rating: Int!
  comment: String
}
~~~

If the `reviews` property is already available on the Java object and can be read directly, GraphQL can use default property access. If related data needs to be queried, write a resolver for the field:

~~~java
@Controller
public class BookFieldController {

    private final ReviewService reviewService;

    public BookFieldController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @SchemaMapping(typeName = "Book", field = "reviews")
    public List<Review> reviews(Book book) {
        return reviewService.findByBookId(book.id());
    }
}
~~~

The `Book` parameter is the source object. The resolver returns a `Review` collection; GraphQL continues resolving the fields of each `Review` according to the selection set.

Nested lists can also appear inside input or output objects. However, if a relationship field may contain thousands of elements, design pagination arguments rather than always returning the entire collection.

## Returning DTOs instead of persistence entities

A repository can return JPA/Hibernate entities, but entities should not always be exposed directly to GraphQL. Entities may contain lazy relationships, proxies, internal fields, or data that should not be public. A cleaner option is converting entities to DTOs before returning them:

~~~java
public record BookSummary(
        String id,
        String title,
        Integer publishedYear) {
}
~~~

~~~java
public interface BookEntityRepository extends JpaRepository<BookEntity, String> {
}

@Service
public class BookService {

    private final BookEntityRepository repository;

    public BookService(BookEntityRepository repository) {
        this.repository = repository;
    }

    public List<BookSummary> findAll() {
        return repository.findAll().stream()
                .map(entity -> new BookSummary(
                        entity.getId(),
                        entity.getTitle(),
                        entity.getPublishedYear()))
                .toList();
    }
}
~~~

Corresponding schema:

~~~graphql
type Query {
  books: [BookSummary!]!
}

type BookSummary {
  id: ID!
  title: String!
  publishedYear: Int
}
~~~

DTOs help control exposed fields, decouple the schema from the persistence model, and prevent GraphQL from accidentally accessing internal properties. If mapping needs to read lazy relationships, perform it inside a transaction or use appropriate projections/queries so the needed data is loaded intentionally.

In this example, the repository uses `JpaRepository` so `findAll()` returns `List<BookEntity>`. If the repository only extends `CrudRepository`, `findAll()` has type `Iterable`; in that case, iterate the `Iterable` or convert it to a `List` before calling `stream()`.

## Collections and the N+1 problem

A resolver returning a collection can cause GraphQL to invoke a child resolver for each element. For example, a `Query` returns 100 `Book` items and the client selects the `author` field:

~~~graphql
type Book {
  id: ID!
  title: String!
  author: Author!
}
~~~

If each resolution of `author` makes a separate database call, one query can trigger 1 query to fetch the list of books and 100 queries to fetch authors. This is the N+1 problem.

Spring for GraphQL supports `@BatchMapping` and DataLoader to batch related data loading:

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

The batch service should load authors by a group of IDs instead of repeating a query for each `Book`. With batch mapping, ensure results are mapped to the exact source objects; if using DataLoader directly, preserve the exact relationship between keys and values.

Large collections not only cost query count but also consume memory and serialization time. Combine batching with pagination and operation complexity limits.

## Pagination instead of returning unbounded collections

A field returning an entire collection works for small datasets, but not for catalogs that can grow continuously. You can add `page` and `size` arguments:

~~~graphql
type Query {
  books(page: Int = 0, size: Int = 20): [Book!]!
}
~~~

~~~java
@QueryMapping
public List<BookSummary> books(
        @Argument Integer page,
        @Argument Integer size) {
    int safePage = Math.max(page == null ? 0 : page, 0);
    int safeSize = Math.min(Math.max(size == null ? 20 : size, 1), 100);
    return bookService.findPage(safePage, safeSize);
}
~~~

The server must enforce a maximum `size` itself; never trust values sent by the client. For APIs that also need to return page metadata, you can define a wrapper object:

~~~graphql
type BookPage {
  content: [BookSummary!]!
  page: Int!
  size: Int!
  hasNext: Boolean!
}

type Query {
  bookPage(page: Int = 0, size: Int = 20): BookPage!
}
~~~

Example Java DTO:

~~~java
public record BookPage(
        List<BookSummary> content,
        int page,
        int size,
        boolean hasNext) {
}
~~~

The wrapper lets clients know whether there is a next page without loading the entire collection. For frequently changing data or when stable navigation is required, cursor pagination / the connection pattern may fit better than offset pagination.

Do not assume Spring Data's `Page<T>` is a GraphQL list. `Page<T>` is an object containing content and pagination metadata; if the schema needs a plain list, return `page.getContent()`. If you want to expose metadata, design an explicit GraphQL wrapper object and DTO.

## Collection return types and reactive types

In Spring for GraphQL, a resolver can return synchronous or reactive results depending on the application's stack. Distinguish a materialized collection from a publisher emitting items:

| Return type | Meaning |
| --- | --- |
| List<Book> | A list already available when the method returns |
| Collection<Book> | A collection already available, not necessarily committed to List |
| Mono<List<Book>> | A single asynchronous result containing the entire list |
| Flux<Book> | A publisher emitting multiple elements under the reactive model |

For a `Query` field needing a list, `List<T>` is the simple choice when data is already loaded synchronously. If the service is reactive, use a reactive return type supported by Spring for GraphQL and ensure underlying operations are also non-blocking. For a `Subscription`, `Flux<T>` typically represents a stream of events over time; these semantics differ from a collection returned all at once.

Do not call `block()` to force a `Mono` or `Flux` into a collection inside a WebFlux resolver. Blocking can stall the event loop and negate reactive benefits. Also do not assume `Flux` and `List` have identical semantics; test queries and subscriptions under the application's actual transport and operation type.

## Return types to handle with caution

Certain Java types are not good choices for GraphQL lists:

- **Stream:** is a single-use traversal stream and may require closing resources. Materialize it into a `List` in the service or use a supported reactive publisher.
- **Iterator:** only traverses current state and may be consumed once. `List` is usually clearer.
- **Map:** GraphQL usually treats it as an object with fields by key, not a list of elements. If you need a list, return a `Collection`; if you need a structured object, define a clear object type.
- **Page or Slice:** contains pagination metadata. Convert to a list or a GraphQL wrapper instead of treating it as a plain list.
- **Lazy entity collections:** can trigger unexpected queries or fail once the persistence context is closed. Convert to DTOs or load relationships intentionally.

## Testing collection return types

You can use `GraphQlTester` to verify a field returns a list and elements are resolved properly:

~~~java
graphQlTester.document("""
        query {
            books {
                id
                title
            }
        }
        """)
    .execute()
    .path("books")
    .entityList(BookSummary.class)
    .hasSize(2);
~~~

You should test:

- Collections with multiple elements and correct ordering.
- Empty collections returning `[]`.
- Null values for list fields and null elements according to SDL nullability.
- `Set` or unordered data sources being stably sorted before returning.
- Nested collections working without unexpected N+1 queries.
- Pagination capping page size and returning accurate metadata.
- Reactive publishers handled properly for their corresponding query or subscription.

When checking nullability, create separate tests for each case because GraphQL can propagate null up to the parent according to propagation rules. Checking only element count is not enough to confirm the `[Book!]!` contract is respected.

## Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| List field returns null | Resolver or service returns null | Return an empty collection when there are no results |
| GraphQL error when a null element is present | SDL declares non-null elements | Filter out or handle null elements before returning |
| Response order changes | Using `Set` or query without `ORDER BY` | Define sorting and return an ordered `List` |
| Lazy initialization error | Entity relation read after transaction closes | Use DTO/projection or load relationships inside transaction |
| Many queries per element | Child resolver calls repository individually | Use `@BatchMapping` or DataLoader |
| Response too large | Returning full collection without pagination | Add pagination and size limits |
| Using `Page` as a list | Confusing pagination wrapper with collection | Return content or define a GraphQL page type |
| Event loop blocked | Blocking a reactive publisher | Keep the pipeline reactive end-to-end |

## Principles for designing collection return types

When designing fields that return lists in Spring for GraphQL, apply these principles:

1. **Declare lists and nullability explicitly.** Distinguish nullable lists, nullable elements, and empty lists.
2. **Prefer `List` when ordering matters.** GraphQL responses preserve the order returned by the resolver.
3. **Return an empty collection when there is no data.** Do not use null instead of an empty list unless the schema requires it.
4. **Use DTOs or projections.** Control exposed data and avoid relying on lazy entities.
5. **Batch nested relationships.** Use `@BatchMapping` or DataLoader to prevent N+1.
6. **Paginate large lists.** Limit page size and consider cursor pagination when appropriate.
7. **Choose the right synchronous or reactive type.** Do not block publishers in reactive applications.
8. **Test null propagation and ordering.** Getting the right item count is not enough; verify the full list contract.

Collection return types connect collections of results in Java with list types in GraphQL. SDL defines the structure and nullability; the resolver supplies the collection; the GraphQL runtime resolves each element and preserves result order. By choosing an ordered `List`, returning appropriate DTOs, handling empty collections, batching relationships, and paginating large datasets, the API becomes more predictable and efficient to operate.
