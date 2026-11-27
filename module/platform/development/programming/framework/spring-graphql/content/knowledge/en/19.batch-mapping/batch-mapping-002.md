# Batch mapping for nested fields

## Objectives

After this lesson, you will be able to:

- Explain why nested field resolvers easily cause the N+1 problem.
- Use @BatchMapping to group the resolution of multiple source objects into a single batch.
- Write batch methods returning Map or List conforming to the Spring for GraphQL contract.
- Understand how DataLoader collects keys, handles duplicate keys, and caches within a single execution.
- Choose a batch size and handle non-existent relationships.
- Test GraphQL responses and the number of service/repository calls.

## Nested fields and the N+1 problem

GraphQL allows clients to query nested fields on demand. For example, a query fetching multiple books and the author information for each book:

~~~graphql
type Query {
  books(first: Int!): [Book!]!
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

Client:

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

A regular resolver for Book.author could be written as:

~~~java
@Controller
public class BookFieldController {

    private final AuthorService authorService;

    public BookFieldController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.authorId()).orElse(null);
    }
}
~~~

This resolver is invoked separately for each Book. If the query returns 3 books, the application may run one query to fetch the list of books and 3 more queries to fetch the authors. With 100 books, the number of queries can grow to 1 + 100.

This is the N+1 problem: one initial query fetches N objects, and then each object triggers an additional query to fetch the nested field's data. GraphQL does not automatically batch repository calls simply because they occur within the same operation.

N+1 does not only happen with databases. If a resolver calls a REST service, gRPC service, or another remote system for each parent object, network round-trips can increase in the same way.

## How does @BatchMapping solve the problem?

Spring for GraphQL provides @BatchMapping to resolve a nested field for multiple source objects at once. Instead of receiving one Book and returning one Author, a batch method receives a list of Books and returns the corresponding results for the entire list.

Example:

~~~java
@Controller
public class BookFieldController {

    private final AuthorService authorService;

    public BookFieldController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public List<Author> author(List<Book> books) {
        List<String> authorIds = books.stream()
                .map(Book::authorId)
                .filter(Objects::nonNull)
                .distinct()
                .toList();

        Map<String, Author> authorsById =
                authorService.findAllByIds(authorIds).stream()
                        .collect(Collectors.toMap(
                                Author::id,
                                Function.identity()));

        return books.stream()
                .map(book -> authorsById.get(book.authorId()))
                .toList();
    }
}
~~~

The batch method receives all Books that need the author field resolved. The service queries authors by a set of authorIds, and then the method constructs the result list in the exact order of the input Book list.

With a query fetching 100 books, instead of calling AuthorService 100 times, the batch method can call findAllByIds once for the required set of IDs. The actual number of queries depends on batch size, pagination, database limits, and DataLoader configuration.

@BatchMapping is a Spring for GraphQL shortcut for combining field mapping with DataLoader. Spring registers a batch loader for the field and uses it to resolve the nested field. You do not need to manually create a DataLoaderRegistry or call dispatch in standard cases.

Do not declare another @SchemaMapping for the same Book.author field. @BatchMapping already handles mapping that field. Two competing resolvers for the same field will cause conflicts or ambiguous configuration.

## Rules for mapping sources and results

A batch method must return results that can be accurately matched to each source object. Spring for GraphQL supports two common result forms:

1. A Map from source object to field value.
2. A List of field values ordered to correspond to the input list of source objects.

### Returning a List in source order

The previous example returns List<Author>. If the batch method receives:

~~~text
books = [bookA, bookB, bookC]
~~~

then the result list must have the exact same number of elements and order:

~~~text
authors = [authorA, authorB, authorC]
~~~

The element at index i is the result of the author field on the source object at index i. If a book has no author or the author does not exist and the schema allows it, the corresponding position can contain null.

Do not sort the author list by name or ID and return it directly. DataLoader has no way to know where an element was moved if a List result no longer preserves source order.

A safe approach is to query by a set of IDs to build a lookup Map, then rebuild the List following the original Book list. This leverages bulk querying while preserving order.

### Returning a Map keyed by source object

When you want to avoid relying on ordering, you can return Map<Book, Author>:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    List<String> authorIds = books.stream()
            .map(Book::authorId)
            .filter(Objects::nonNull)
            .distinct()
            .toList();

    Map<String, Author> authorsById =
            authorService.findAllByIds(authorIds).stream()
                    .collect(Collectors.toMap(
                            Author::id,
                            Function.identity()));

    Map<Book, Author> result = new HashMap<>();
    for (Book book : books) {
        Author author = book.authorId() == null
                ? null
                : authorsById.get(book.authorId());
        if (author != null) {
            result.put(book, author);
        }
    }
    return result;
}
~~~

The Map key is the Book source object passed into the batch method; the value is the corresponding Author. With a mapped batch loader, keys absent from the Map are treated as having no corresponding value and resolve to null.

When using a Map, ensure the key type has stable equals/hashCode semantics. If Book is a JPA entity, be careful with equals/hashCode based on an unassigned ID or an entity proxy. If you are unsure about source object equality, the order-preserving List form is usually easier to control.

Do not return Map<String, Author> just because the service looks up by authorId. Batch mapping needs results associated with each Book source object, not just with the author's ID. You can use Map<String, Author> as an intermediate lookup structure as in the example, then convert it to Map<Book, Author> or List<Author> at the final step.

## Non-existent relational data

In the example, the Book.author field is declared nullable:

~~~graphql
type Book {
  id: ID!
  title: String!
  author: Author
}
~~~

If a Book has no authorId or the author has been deleted, the batch method can return null for that field. With the List form, keep null at the corresponding source index. With the Map form, omit keys with no result so DataLoader resolves the missing value to null.

If the schema declares author: Author!, the server must ensure every returned Book has a valid Author. When the batch method cannot find an author for a book, a null result violates non-null constraints and GraphQL applies null propagation. Do not declare a field non-null merely because most existing records happen to have an author.

Distinguish between:

- No valid relationship exists: return null if the schema and business rules allow it.
- The repository or downstream service fails: raise an error for GraphQL to handle; do not turn infrastructure errors into null.
- Data violates an invariant: log and handle it as a data error rather than silently ignoring it if doing so hides an incident.

## BatchMapping and DataLoader

DataLoader is a mechanism for combining multiple data requests into a batch. When resolvers request an author for multiple Books, DataLoader records the keys to load. At the dispatch point of GraphQL execution, the batch loader is called with the accumulated keys and returns the corresponding results.

With @BatchMapping, Spring for GraphQL creates and registers the required DataLoader for the field. General flow:

~~~mermaid
flowchart TD
    A[Query fetches Book list] --> B[GraphQL resolves Book.author]
    B --> C[DataLoader records each Book key]
    C --> D[GraphQL dispatches batch]
    D --> E[@BatchMapping receives List<Book>]
    E --> F[Collect unique authorIds]
    F --> G[AuthorService queries in bulk]
    G --> H[Build results per Book]
    H --> I[DataLoader completes each field]
    I --> J[GraphQL builds response]
~~~

DataLoader also supports caching by key within the scope of a single execution. If multiple branches of the same operation need the same key, DataLoader can reuse the already-loaded result instead of calling the batch loader repeatedly. This cache is typically scoped per request/execution and should not be replaced by a global cache holding user- or tenant-dependent data.

Batching and caching reduce data access frequency, but they do not replace efficient query design. The batch method still needs to query the right dataset and avoid loading unnecessary columns or records.

## Handling duplicate IDs and nulls

Multiple Books can share the same authorId. When querying the repository, deduplicate IDs so the same author is not loaded multiple times:

~~~java
List<String> authorIds = books.stream()
        .map(Book::authorId)
        .filter(Objects::nonNull)
        .distinct()
        .toList();
~~~

DataLoader can handle duplicate keys during loading and caching, but the batch method should still construct the query from a set of unique IDs to reduce work in the repository layer. The final results must still be mapped to every Book, even when multiple Books reference the same Author.

Do not include null in the query ID list. If the relational field is nullable, skip sources without an ID when building the key set and return null for those sources.

When the source list is empty, calling the repository is usually unnecessary. The batch method can return the corresponding empty collection.

## Limiting batch size

A very large batch can exceed database parameter limits or produce overly heavy queries. @BatchMapping supports the maxBatchSize attribute to limit the number of source keys in a single batch:

~~~java
@BatchMapping(
        typeName = "Book",
        field = "author",
        maxBatchSize = 100)
public List<Author> author(List<Book> books) {
    // Query and return results in the exact order of books.
}
~~~

When the number of keys exceeds the limit, DataLoader splits them into smaller batches. For example, 250 sources with a maxBatchSize of 100 may be processed as batches of 100, 100, and 50. This is a limit per batch dispatch, not a pagination limit on the root query.

Choose maxBatchSize based on database limits, SQL statement size, downstream service latency, and returned payload size. Do not set a huge value just to minimize batch count; oversized batches can increase memory usage, query duration, and system load.

If the bulk query service has its own limit, ensure maxBatchSize is compatible. If a batch needs to be split further due to repository limits, you can chunk inside the service and merge results before returning from the batch method.

## Batching multiple nested fields

A schema may have multiple relationships that need batch loading. For example, Book has both author and publisher:

~~~graphql
type Book {
  id: ID!
  title: String!
  author: Author
  publisher: Publisher
}
~~~

You can declare two separate batch mappings:

~~~java
@Controller
public class BookRelationController {

    private final AuthorService authorService;
    private final PublisherService publisherService;

    public BookRelationController(
            AuthorService authorService,
            PublisherService publisherService) {
        this.authorService = authorService;
        this.publisherService = publisherService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public List<Author> author(List<Book> books) {
        // Bulk load authors and preserve source order.
        return authorService.findForBooks(books);
    }

    @BatchMapping(typeName = "Book", field = "publisher")
    public List<Publisher> publisher(List<Book> books) {
        // Bulk load publishers and preserve source order.
        return publisherService.findForBooks(books);
    }
}
~~~

Each field has its own batch loader. If the client only selects author, the publisher resolver does not need to run. If the client selects both, GraphQL can batch requests for each field via its respective DataLoader.

For deeper relationships like Author.organization, you can create a batch mapping on Author. Each level of nested fields can have its own batch loader; monitor batch counts and query counts across the entire operation to avoid merely shifting N+1 from one relationship to another.

## When to use @BatchMapping vs. explicit DataLoader?

@BatchMapping is appropriate when:

- You need to resolve a field of an object type for multiple source objects of the same type.
- The batch key is the source object itself.
- Results can be returned as Map<Source, Value> or List<Value> in source order.
- You want Spring for GraphQL to register the DataLoader for the field automatically.

Explicit DataLoader is appropriate when:

- Multiple fields or resolvers need to share the same type of loader.
- The key for loading data is an ID or another structure, not the source object.
- You need to customize loader registration, context, or caching strategy.
- You need to use the same batch loader outside a simple mapping.

Example of a resolver using an injected DataLoader:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(
        Book book,
        DataLoader<String, Author> authorLoader) {
    return authorLoader.load(book.authorId());
}
~~~

With this approach, the DataLoader uses authorId as its key. The application needs to register the corresponding loader using BatchLoaderRegistry or an appropriate DataLoader configuration mechanism. Do not also register a @BatchMapping for the same Book.author field.

If you only need to batch source objects for a single field, @BatchMapping is usually shorter and easier to read. When keys, caching, or loader sharing have specific requirements, consider an explicit DataLoader.

## Testing BatchMapping

You should verify both the response and the number of times the batch service is called. For example, a query fetching multiple books:

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

A test with GraphQlTester can verify the nested field data:

~~~java
graphQlTester.document("""
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
        """)
    .execute()
    .path("books[0].author.name")
    .entity(String.class)
    .isEqualTo("Nguyen An");
~~~

Beyond the response, use Mockito or a spy to verify the bulk service is called in batches rather than once per Book. For example, with one batch:

~~~java
verify(authorService, times(1))
        .findAllByIds(anyList());
~~~

The actual call count depends on the number of batches, maxBatchSize, and execution. If the test has only three books and maxBatchSize is greater than three, expecting one bulk service call is reasonable. Do not hardcode an assertion of one call if the test fixture intentionally exceeds the batch limit.

You should test:

1. Multiple Books are returned and nested authors are matched properly.
2. Multiple Books sharing the same authorId do not corrupt results.
3. A batch method returning a List preserves source order.
4. A batch method returning a Map matches the exact source object.
5. A Book with no authorId or a non-existent author resolves to null when the schema is nullable.
6. Batches exceeding maxBatchSize are split into an appropriate number of loads.
7. When the client does not select the nested field, the batch service is not called.
8. A query with multiple nested relations only invokes the required loaders.
9. Errors from the bulk service become GraphQL errors per application policy.

In a @GraphQlTest slice test, include the controller containing @BatchMapping in the context and mock the service. Integration tests with a full application context are useful for verifying DataLoader configuration and real repositories.

## Common pitfalls

| Symptom | Possible cause | Solution |
| --- | --- | --- |
| Still seeing N+1 after adding @BatchMapping | Batch method was not detected or field mapping does not match | Check @Controller, typeName, field, and schema |
| Author results matched to wrong books | Returned List does not preserve source order | Rebuild results in input Book list order or use a Map |
| Some nested fields are always null | Map key does not match source object or relation not found | Check equals/hashCode and ID data |
| Batch query returns duplicate results | Duplicate IDs not removed when querying in bulk | Use distinct on keys and map results back to each source |
| Repository still called too many times | Batch size too small or loader not batching within the same execution | Check maxBatchSize, loader registration, and execution scope |
| Service still runs when query omits author | Logic calls service outside the batch mapping | Load nested data only when the field is requested |
| Batch method and @SchemaMapping conflict | Both registered for the same field | Keep only one resolver for that field |
| Cache returns data for the wrong user | Shared cache outside the request used for permission-dependent data | Keep DataLoader cache in execution scope and include tenant/user context in key strategy when needed |
| Batch exceeds database limit | One batch contains too many keys | Limit maxBatchSize or chunk in the service |

## Comprehensive practice

Build a library API with a list of books and two nested relations:

1. The books query returns a paginated list of Books.
2. Book.author is resolved using @BatchMapping.
3. Book.publisher is also resolved using another @BatchMapping.
4. AuthorService and PublisherService provide bulk methods accepting a list of IDs.
5. Use a lookup Map by ID in the service and construct results in the exact order of the input Books.
6. Handle books without an author or publisher according to SDL nullability.
7. Configure maxBatchSize appropriately for query limits.
8. Write a GraphQlTester test verifying responses and Mockito verify on bulk service call counts.
9. Compare query counts when using @SchemaMapping calling the repository per book versus using @BatchMapping.

After completing the exercise, explain why DataLoader batches requests within the same execution, why a List must preserve source order, and when a Map is the safer choice.

## Takeaways

Nested fields can cause N+1 when each parent object triggers a separate query. @BatchMapping allows Spring for GraphQL to accept multiple source objects, collect keys, and load data in bulk via DataLoader. A batch method can return a Map linking sources to results or a List whose order matches the source list exactly. Deduplicate keys, handle missing relationships according to nullability, limit batch sizes to match downstream constraints, and test both the returned data and service call counts. Use an explicit DataLoader when custom keys or caching are needed; for a straightforward nested field, @BatchMapping is usually the most direct choice.
