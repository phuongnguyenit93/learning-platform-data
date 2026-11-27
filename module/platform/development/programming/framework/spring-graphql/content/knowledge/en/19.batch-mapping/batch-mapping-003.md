# List source objects

In GraphQL, a nested field is typically resolved for each parent object. If a query returns a list of multiple Books and the client selects the Author of each Book, a regular resolver receives one Book per call. **@BatchMapping** changes how data is received: the handler receives a list of source objects to load the relationship in bulk.

This list is not an argument sent by the client. It consists of the parent objects for which GraphQL Java needs to resolve the same field in a batch round. Spring for GraphQL uses DataLoader under the hood to collect field resolution requests, call the batch handler with the list of source objects, and then distribute the results back to each object's field.

This lesson focuses on the meaning of the **List<Source>** parameter in @BatchMapping, how the source type is determined, how to return results via Map or List, preserving the relationship between input and output, handling one-to-many relationships, batch size limits, and testing.

## 1. What is a source object?

A source object is a value returned from a parent field that becomes the input for resolving a child field.

Schema example:

~~~graphql
type Query {
  books(first: Int = 20): [Book!]!
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

Root resolver:

~~~java
@QueryMapping
public List<Book> books(@Argument Integer first) {
    return bookService.findFirst(first);
}
~~~

When the client sends:

~~~graphql
query {
  books(first: 3) {
    id
    title
    author {
      id
      name
    }
  }
}
~~~

The Query.books field returns three Book objects. Each Book object is a source object for the Book.author field.

With a regular resolver:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

The method receives one Book per call. If there are three Books, the method may be called three times. If each call queries the database, the application can suffer from N+1.

## 2. List source objects in @BatchMapping

Spring for GraphQL provides **@BatchMapping** to group multiple source objects that need the same field resolved. Instead of receiving one Book, the handler receives List<Book>:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    // Load Author for the entire group of Books
    return authorService.findAuthorsForBooks(books);
}
~~~

What the **List<Book> books** parameter means:

- Each element is a source object for the Book.author field.
- The list is collected by the framework from field resolution calls that need batching.
- The handler can extract the required keys from all Books.
- The handler loads related data in bulk.
- The results are mapped back to each source Book.

This list is not an argument like **ids: [ID!]!** in the SDL. The client does not send List<Book> to the handler. Spring for GraphQL provides it from GraphQL execution via the batch loader.

### Processing flow

~~~mermaid
flowchart TD
    A[Query.books] --> B[List of Books]
    B --> C1[Book 1 needs Author]
    B --> C2[Book 2 needs Author]
    B --> C3[Book 3 needs Author]
    C1 --> D[DataLoader collects source objects]
    C2 --> D
    C3 --> D
    D --> E[@BatchMapping List<Book>]
    E --> F[Batch query Authors]
    F --> G[Result Map or List]
    G --> H[Distribute Author to each Book]
    H --> I[GraphQL response]
~~~

For a batch of three Books, the batch handler is invoked once for that group instead of calling the resolver three separate times. If batch size limits or execution produce multiple dispatch rounds, the handler may be called multiple times; do not assume a query always triggers exactly one batch call.

## 3. Comparing source objects and client arguments

Two kinds of List can appear in a handler signature, carrying different meanings.

SDL:

~~~graphql
type Query {
  booksByIds(ids: [ID!]!): [Book!]!
}
~~~

Root handler:

~~~java
@QueryMapping
public List<Book> booksByIds(@Argument("ids") List<String> ids) {
    return bookService.findAllByIds(ids);
}
~~~

Here **List<String> ids** is an argument sent by the client and marked with **@Argument**.

In a batch handler:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    return authorService.findAuthorsForBooks(books);
}
~~~

**List<Book> books** is the list of source objects collected by Spring for GraphQL. It is not an argument of the Book.author field.

| Parameter signature | Data source |
|---|---|
| **@Argument("ids") List<String> ids** | Argument from the GraphQL operation |
| **List<Book> books** in @BatchMapping | Source objects collected from the parent field |
| **Book book** in @SchemaMapping | A single source object for one resolution |

Distinguishing the data source correctly avoids misplacing @Argument annotations or mistakenly thinking the client must send the list of parent objects.

## 4. How does Spring infer the source type and field?

In @BatchMapping, Spring can infer the type owning the field from the generic type of the source list parameter and infer the field name from the method name.

Example:

~~~java
@BatchMapping
public Map<Book, Author> author(List<Book> books) {
    return authorService.findAuthorsForBooks(books);
}
~~~

The framework can infer:

- The source type is **Book** from List<Book>.
- The field is **author** from the method name.

For a clearer mapping, you can specify them explicitly:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> loadAuthors(List<Book> books) {
    return authorService.findAuthorsForBooks(books);
}
~~~

The Java method name does not need to match the field name once field is declared explicitly.

If a controller contains multiple batch mappings for the same source type, explicit declaration helps readers quickly see which mapping handles which field.

## 5. Returning results via Map<Source, Value>

A common approach is returning a Map where the key is the source object and the value is the resolved field value.

Model example:

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

Batch mapping:

~~~java
@Controller
public class BookBatchController {

    private final AuthorService authorService;

    public BookBatchController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        List<String> authorIds = books.stream()
                .map(Book::authorId)
                .distinct()
                .toList();

        Map<String, Author> authorsById =
                authorService.findAllByIds(authorIds);

        Map<Book, Author> result = new HashMap<>();
        for (Book book : books) {
            result.put(book, authorsById.get(book.authorId()));
        }
        return result;
    }
}
~~~

The batch handler performs two steps:

1. Extract authorId from all Books and remove duplicate IDs.
2. Query Authors by the ID list, then map the results back to each Book.

Example SQL the service might use:

~~~sql
SELECT id, name
FROM author
WHERE id IN (?, ?, ?);
~~~

If there are three Books referencing only two distinct Authors, the batch query only needs to load two IDs. Each Book still receives its corresponding Author from the result Map.

### Map keys must correspond to source objects

With the Map<Book, Author> form, keys must match the Book source objects passed to the batch loader. When using regular Java classes or JPA entities, pay attention to equals and hashCode so keys behave reliably.

Java records provide equals/hashCode automatically based on their components. For entities whose equals/hashCode depend on an ID generated after persistence, understand the behavior clearly before using them as Map keys. If you do not want to rely on entity equality, return a List in the exact order of the source input.

### Do not rely on database return order

A database does not guarantee result order if the SQL query has no ORDER BY. Do not take the returned list of Authors and assume the first element corresponds to the first Book.

Build a Map by ID or source object to map accurately regardless of the order returned by the database.

## 6. Returning results via List in exact source order

A batch handler can also return a List. When using this form, the element at index i must be the result corresponding to the source object at index i in the input list.

Example:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public List<Author> author(List<Book> books) {
    List<String> authorIds = books.stream()
            .map(Book::authorId)
            .distinct()
            .toList();

    Map<String, Author> authorsById =
            authorService.findAllByIds(authorIds);

    List<Author> result = new ArrayList<>(books.size());
    for (Book book : books) {
        result.add(authorsById.get(book.authorId()));
    }
    return result;
}
~~~

Suppose the source list is:

| Index | Source Book | authorId |
|---:|---|---|
| 0 | Book A | author-01 |
| 1 | Book B | author-02 |
| 2 | Book C | author-01 |

The batch result must preserve the exact positions:

| Index | Required result |
|---:|---|
| 0 | Author of Book A |
| 1 | Author of Book B |
| 2 | Author of Book C |

Book A and Book C share the same authorId, so they can share the same Author object in the result, but it must still appear at both positions.

Do not:

- Sort the Author list by name and return it directly.
- Omit an element when an Author is not found.
- Return only non-null results.
- Return a List with a different size than the source object list.

If an element in the middle is omitted, subsequent values will be matched to the wrong parent. When handling missing links, keep the slot with a null element or use a Map with explicit keys.

### Choosing Map or List?

| Criterion | Map<Source, Value> | List<Value> |
|---|---|---|
| Result matching | By source key | By index |
| Order dependency | Independent of result order | Must preserve input order |
| equals/hashCode requirement | Requires stable key behavior | Does not use source as a Map key |
| Missing data cases | Can omit key or map null | Must preserve corresponding position |
| Code readability | Explicitly shows source-result relationship | Concise when order is easy to preserve |

If query results have non-deterministic order or entities lack stable equality, a Map is often easier to manage. If you can build results in the exact order of the source list, a List is a straightforward choice.

## 7. Batch mapping for one-to-many relationships

Not only Book.author can be batched. A Book can have many Reviews:

~~~graphql
type Book {
  id: ID!
  title: String!
  reviews: [Review!]!
}

type Review {
  id: ID!
  content: String!
}
~~~

The batch handler can return Map<Book, List<Review>>:

~~~java
@BatchMapping(typeName = "Book", field = "reviews")
public Map<Book, List<Review>> reviews(List<Book> books) {
    List<String> bookIds = books.stream()
            .map(Book::id)
            .toList();

    Map<String, List<Review>> reviewsByBookId =
            reviewService.findAllByBookIds(bookIds);

    Map<Book, List<Review>> result = new HashMap<>();
    for (Book book : books) {
        List<Review> reviews = reviewsByBookId.getOrDefault(
                book.id(),
                List.of());
        result.put(book, reviews);
    }
    return result;
}
~~~

The service can load reviews for multiple Books in a single query:

~~~sql
SELECT id, book_id, content
FROM review
WHERE book_id IN (?, ?, ?)
ORDER BY book_id, id;
~~~

Then group Reviews by bookId and return the list for each source Book.

For one-to-many relationships, return an empty list when a parent has no child elements if the SDL declares the list non-null. For example, **[Review!]!** requires the field to always have a list with no null elements. An empty list is a valid result.

If the schema field allows a null list, deciding between returning null or an empty list must reflect domain semantics. Do not use null and empty list interchangeably without reason.

## 8. Batch size and multiple handler invocations

Do not assume all source objects of an operation are always delivered in a single List. DataLoader can dispatch in multiple rounds and can limit batch size.

**@BatchMapping** supports the **maxBatchSize** attribute to limit the number of source objects in a batch:

~~~java
@BatchMapping(
        typeName = "Book",
        field = "author",
        maxBatchSize = 100)
public Map<Book, Author> author(List<Book> books) {
    return authorService.findAuthorsForBooks(books);
}
~~~

With this configuration, each invocation of the batch handler receives at most 100 source objects. If there are more, the loader can split them into multiple batches.

Limiting batch size is useful when:

- The database restricts the number of bind parameters.
- Overly large batch queries increase memory or processing time.
- Downstream services limit the number of keys per request.
- You need to control internal payload size between GraphQL and the data layer.

Too small a batch size increases the number of batch calls. Too large a batch size can generate huge queries and consume excessive memory. Choose based on database limits, data volume, and measured metrics.

If maxBatchSize is not specified, default behavior depends on DataLoader configuration and library version. Check the version of Spring for GraphQL you are using before relying on a specific limit.

## 9. Batch handlers can run asynchronously

Spring for GraphQL supports asynchronous and reactive return types for handler methods. A batch handler can load data from an asynchronous service if the data access layer supports it.

Example illustrated with Mono:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Mono<Map<Book, Author>> author(List<Book> books) {
    List<String> authorIds = books.stream()
            .map(Book::authorId)
            .distinct()
            .toList();

    return authorService.findAllByIdsAsync(authorIds)
            .map(authorsById -> {
                Map<Book, Author> result = new HashMap<>();
                for (Book book : books) {
                    result.put(
                            book,
                            authorsById.get(book.authorId()));
                }
                return result;
            });
}
~~~

This example assumes the service returns **Mono<Map<String, Author>>**. The batch result completes only when the service finishes. Choose reactive types compatible with your application stack and avoid blocking threads by calling a blocking repository inside a reactive pipeline.

If using blocking JPA/JDBC, a synchronous method may be more appropriate; do not wrap a blocking call in Mono just to appear reactive.

## 10. Handling empty source lists and missing data

In practice, a batch handler should explicitly handle cases where there are no source objects or no related data.

### Empty source list

If no parent requests the field, the batch loader normally does not need to execute a query. If the handler is invoked with an empty list in a particular situation, do not call the repository with an empty list when the SQL dialect or service API does not support it.

You can guard with:

~~~java
if (books.isEmpty()) {
    return Map.of();
}
~~~

### Child object not found

Suppose a Book references an authorId that no longer exists. There are two main options:

- If the Book.author field is nullable, return null for that Book.
- If the Book.author field is non-null, missing data is an error that must be handled per domain rules and GraphQL nullability.

With a Map, you can omit the key or put the key with a null value depending on the contract and how the loader handles it. With a List, you must keep a null element at the exact index if the field allows it.

For one-to-many relationships, having no Reviews is normally represented by an empty list.

Do not drop source objects from the result. The batch loader must be able to map results back to each input key.

## 11. Avoiding assumptions about repository result ordering

A common mistake is collecting a list of source IDs, calling the repository, and returning the result list directly:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public List<Author> author(List<Book> books) {
    List<String> ids = books.stream()
            .map(Book::authorId)
            .toList();

    return authorRepository.findAllById(ids);
}
~~~

This code is unsafe if the repository does not guarantee results in the same order as the input ID list. Many repository APIs only return the found entities and make no ordering guarantees.

The safe approach is to build a Map by ID:

~~~java
Map<String, Author> authorsById =
        authorService.findAllByIds(ids);

List<Author> result = new ArrayList<>();
for (Book book : books) {
    result.add(authorsById.get(book.authorId()));
}
return result;
~~~

Or return Map<Book, Author>:

~~~java
Map<Book, Author> result = new HashMap<>();
for (Book book : books) {
    result.put(book, authorsById.get(book.authorId()));
}
return result;
~~~

Both approaches preserve the exact parent-child relationship regardless of the order returned by the database.

## 12. How do BatchMapping and DataLoader relate?

**@BatchMapping** is a way to declare a batch field resolver at the annotated controller level. Spring for GraphQL registers a batch loader underneath via DataLoader.

Overview:

| Component | Responsibility |
|---|---|
| Source object | Parent object whose child field needs to be resolved |
| List<Source> | Group of source objects passed into the batch handler |
| @BatchMapping | Declares the field mapping and batch method |
| DataLoader | Collects load requests during execution and coordinates dispatch |
| Batch method | Loads data for the group of source objects |
| Map/List result | Matches returned values to each source |

When you only need to batch a simple field, @BatchMapping reduces manual DataLoader registration boilerplate. If you need to share a loader across multiple controllers, use a key other than the source object, configure custom options, or implement complex dispatch logic, you can register a DataLoader directly via **BatchLoaderRegistry**.

BatchMapping does not mean every database query in a controller is automatically batched. Only fields mapped through batch methods use that batching mechanism.

## 13. Choosing @BatchMapping or @SchemaMapping?

The two annotations serve different handler styles:

| Criterion | @SchemaMapping | @BatchMapping |
|---|---|---|
| Source parameter | One source object | List of source objects |
| Data loading approach | Typically handles one parent at a time | Handles a group of parents |
| Best suited for | Property or logic specific to one object | Relationships that should be loaded in bulk |
| N+1 | Can occur if each invocation queries separately | Helps batch data loading |
| Return value | Single field value | Source-to-value Map or ordered List |

@SchemaMapping example:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorService.findById(book.authorId());
}
~~~

@BatchMapping example:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    return authorService.findAuthorsForBooks(books);
}
~~~

Not every field should be batched. If a field is an existing property on the source object, the default property fetcher may suffice. If a field needs to load data per parent and can be grouped, @BatchMapping is usually a better fit.

## 14. Testing batch methods receiving List source objects

GraphQlTester can verify the response of batched fields. To verify batching behavior, add a spy/mock or query counter for the service called inside the batch method.

Example operation:

~~~graphql
query {
  books(first: 3) {
    id
    title
    author {
      id
      name
    }
  }
}
~~~

Response test:

~~~java
@SpringBootTest
class BookBatchMappingTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void shouldResolveAuthorsForAllBooks() {
        graphQlTester.document("""
                query {
                    books(first: 3) {
                        title
                        author {
                            name
                        }
                    }
                }
                """)
            .execute()
            .path("books")
            .entityList(BookWithAuthorView.class)
            .hasSize(3);
    }
}
~~~

To verify the batch method receives multiple source objects, you can:

1. Mock AuthorService and capture the list of author IDs.
2. Verify the service is called in batch rather than once per Book.
3. Verify duplicate IDs are handled properly.
4. Verify results are returned for the right corresponding Books.
5. Verify cases where the database returns results out of input order.
6. Verify missing children and field nullability.
7. Verify one-to-many relationships return an empty list when there are no children.
8. Verify maxBatchSize if the application configures a limit.
9. Verify async batch methods complete properly and do not block the reactive event loop.
10. Measure SQL query counts to ensure there are no separate queries per source.

Checking only the GraphQL response is not enough to prove N+1 has been eliminated. A batch method could still call the repository in a loop; you must check service/repository call counts or actual SQL statement counts.

## 15. Common mistakes with List source objects

| Symptom | Possible cause | Solution |
|---|---|---|
| Method receives empty List or is not called | Field not selected by client or mapping does not match | Check selection set, typeName, and field |
| Confusing List source with List argument | Mixing up @BatchMapping and @Argument | Source list is provided by the framework; arguments use @Argument |
| Author results attached to wrong Book | Returning List without preserving input order | Build results following the source list or use a Map |
| Missing result for a source | Dropping element when child does not exist | Keep a null position or map the source to null |
| Map cannot find source key | Unstable equals/hashCode on the source object | Use stable equality or return an ordered List |
| N+1 still occurs | Batch method calls service/repository in a loop | Collect keys and query once per group |
| A batch is too large | No limit on key count | Configure maxBatchSize and measure in practice |
| Database results in wrong order | Assuming repository returns in input order | Map by ID before constructing output |
| One-to-many unexpectedly returns null | No children and no empty list created | Use an empty list if required by schema/domain |
| Batch handler is not used | Another DataFetcher is already registered for the same field | Check mappings and runtime wiring |

## 16. Workflow for implementing List source objects

When converting a field resolver to batching:

1. Identify the parent object type and relational field to resolve.
2. Confirm the field is selected by clients for multiple source objects in the same execution.
3. Write a **@BatchMapping** method accepting **List<Source>**.
4. Specify typeName and field explicitly if names cannot be inferred clearly.
5. Extract keys from all source objects.
6. Deduplicate keys if the service/database can load by a set of IDs.
7. Query data in batch; do not call the repository in a loop.
8. Return Map<Source, Value> or List<Value> preserving source order.
9. Handle missing children, nullability, and one-to-many relationships.
10. Choose maxBatchSize based on practical limits when needed.
11. Write GraphQlTester tests and verify service/SQL call counts.
12. Re-measure latency, query count, and memory across different list sizes.

The List source objects parameter is the core of @BatchMapping: it gives the batch handler all parents that need to be resolved as a group. Spring for GraphQL collects source objects via DataLoader, while the handler is responsible for loading data efficiently and matching results back to the right sources. Returning a Map maps by key; returning a List requires preserving the exact order and element count. When the source list is handled properly, queries in loops are avoided, and query counts are tested, batch mapping can reduce N+1 while keeping responses aligned with the schema.
