# Queries with Multiple Fields

A GraphQL query can request multiple top-level fields in a single operation. Instead of sending separate HTTP requests for each type of data, a client can fetch book details, author details, and the latest list in one request, provided those fields are declared on the root `Query` type.

GraphQL Java executes each field according to the schema and selection set. The results are assembled into a `data` object with keys corresponding to field names or aliases. Top-level query fields may be executed independently and in parallel; therefore, the application must not rely on resolver invocation order. If you need to modify data sequentially, use a mutation whose root fields execute sequentially.

## 1. Declaring Multiple Fields on the Root Query

Suppose a book and author management API has the schema:

```graphql
type Query {
    bookById(id: ID!): Book
    authorById(id: ID!): Author
    latestBooks(limit: Int = 10): [Book!]!
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

The root `Query` type has three independent fields: `bookById`, `authorById`, and `latestBooks`. The client can call all three in a single operation:

```graphql
query Dashboard {
    bookById(id: "book-01") {
        id
        title
    }
    authorById(id: "author-01") {
        id
        name
    }
    latestBooks(limit: 5) {
        id
        title
    }
}
```

The server returns a response with a matching structure:

```json
{
  "data": {
    "bookById": {
      "id": "book-01",
      "title": "Spring in Action"
    },
    "authorById": {
      "id": "author-01",
      "name": "Craig Walls"
    },
    "latestBooks": [
      {
        "id": "book-01",
        "title": "Spring in Action"
      }
    ]
  }
}
```

All fields are requested in one operation and returned in the same response. The client does not have to send one request to fetch the book, another to fetch the author, and yet another to fetch the latest list.

## 2. Connecting Each Root Field to a Spring Controller

In Spring for GraphQL, each root field can be handled by a `@QueryMapping` method. You can place the methods in the same controller or split them by domain:

```java
@Controller
public class CatalogQueryController {

    private final BookService bookService;
    private final AuthorService authorService;

    public CatalogQueryController(
            BookService bookService,
            AuthorService authorService) {
        this.bookService = bookService;
        this.authorService = authorService;
    }

    @QueryMapping
    public Book bookById(@Argument("id") String id) {
        return bookService.findById(id);
    }

    @QueryMapping
    public Author authorById(@Argument("id") String id) {
        return authorService.findById(id);
    }

    @QueryMapping
    public List<Book> latestBooks(@Argument("limit") Integer limit) {
        return bookService.findLatest(limit);
    }
}
```

Spring binds each method name to the corresponding field on `Query`. `@Argument` extracts argument values from the operation. If the client does not pass `limit`, the default value `10` in the SDL is applied per GraphQL rules before the resolver receives the argument.

These fields are independent resolvers. GraphQL Java collects them from the selection set and invokes each resolver during operation execution. Child fields such as `Book.author` can be handled with `@SchemaMapping` or `@BatchMapping` depending on data-fetching needs.

## 3. Using Aliases When Calling the Same Field Multiple Times

A query may need to fetch multiple books by different IDs. If you write the same `bookById` field twice without an alias, both occurrences have the same response key. GraphQL requires fields with the same response key to be compatible and mergeable; if their arguments differ, the operation fails with a field conflict error.

Use aliases to create distinct response keys:

```graphql
query CompareBooks($firstId: ID!, $secondId: ID!) {
    firstBook: bookById(id: $firstId) {
        id
        title
    }
    secondBook: bookById(id: $secondId) {
        id
        title
    }
}
```

The response uses the aliases as keys:

```json
{
  "data": {
    "firstBook": {
      "id": "book-01",
      "title": "Spring in Action"
    },
    "secondBook": {
      "id": "book-02",
      "title": "GraphQL in Action"
    }
  }
}
```

An alias only renames the key in the current operation's response. It does not rename the field in the schema and does not create another resolver. Both `firstBook` and `secondBook` still map to the same `Query.bookById` field, each with its own arguments.

Aliases are also useful when calling a nested field multiple times with different arguments:

```graphql
query BookReviews($bookId: ID!) {
    bookById(id: $bookId) {
        positive: reviews(ratingAtLeast: 4) {
            content
        }
        critical: reviews(ratingAtMost: 2) {
            content
        }
    }
}
```

In this example, `positive` and `critical` are two separate response keys for the same `reviews` field. The resolver must support the corresponding arguments.

## 4. Using Variables to Pass Data to Multiple Fields

Variables make operations reusable and separate input data from the GraphQL document. A single operation can declare multiple variables and pass them to different root fields:

```graphql
query Dashboard(
    $bookId: ID!
    $authorId: ID!
    $latestLimit: Int = 5
) {
    selectedBook: bookById(id: $bookId) {
        id
        title
    }
    selectedAuthor: authorById(id: $authorId) {
        id
        name
    }
    latestBooks(limit: $latestLimit) {
        id
        title
    }
}
```

When sending the request, the client provides variables in a separate payload section:

```json
{
  "operationName": "Dashboard",
  "variables": {
    "bookId": "book-01",
    "authorId": "author-01",
    "latestLimit": 8
  }
}
```

GraphQL validates variable types against the schema arguments before execution. If a non-null variable is missing or an incompatible value is passed, the operation fails validation/coercion and the resolvers are not executed as a valid query.

A GraphQL document can contain multiple named operations, but a normal request only executes the operation specified by `operationName`. Multiple root fields in one operation is the way to fetch multiple pieces of data at once; writing multiple operations in one document does not mean the server automatically runs all of them.

## 5. Reusing Selection Sets with Fragments

When multiple root fields return the same type and need the same group of fields, fragments avoid duplicating the selection set:

```graphql
fragment BookSummary on Book {
    id
    title
    author {
        id
        name
    }
}

query CatalogOverview($firstId: ID!, $secondId: ID!) {
    featured: bookById(id: $firstId) {
        ...BookSummary
    }
    recommended: bookById(id: $secondId) {
        ...BookSummary
    }
}
```

The `BookSummary` fragment is applied in two places. GraphQL expands the selection set and executes the required fields for each source object. A fragment only reuses the data selection structure; it does not create a new request or an independent resolver.

You can combine fragments with inline fragments when a field returns an interface or union. Clients select shared fields directly, then use `... on Book` or `... on Article` to retrieve fields specific to each object type.

## 6. How Does GraphQL Collect and Merge Fields?

Before execution, GraphQL parses the document, validates the operation against the schema, and collects selected fields across selection sets. Fields can come from direct selections, named fragments, or inline fragments.

GraphQL uses the **response key** to identify each field in the result. The response key is the alias if present, otherwise the field name. Occurrences sharing the same response key must satisfy field merging rules: they must be compatible in field name, arguments, and selection sets. If there is a conflict, the operation is rejected during validation.

For example, two selections of the same field with the same arguments and response key can be merged into one field group:

```graphql
query {
    bookById(id: "book-01") {
        title
    }
    bookById(id: "book-01") {
        author {
            name
        }
    }
}
```

Compatible selection sets are combined so the `bookById` result includes both `title` and `author.name`. However, for readability, it is usually best to write the field once with the complete selection set:

```graphql
query {
    bookById(id: "book-01") {
        title
        author {
            name
        }
    }
}
```

If you want the same field called with different arguments, give them different aliases as in the `firstBook` and `secondBook` example.

## 7. How Are Multiple Root Fields Executed?

By GraphQL rules, the top-level fields of a query may be executed in parallel. This allows the server to process independent pieces of data without waiting for the previous field to finish. GraphQL Java uses a query execution strategy to coordinate fields; asynchronous results such as `CompletableFuture` can be processed concurrently.

However, do not assume every synchronous Java call necessarily runs on separate threads. Actual concurrency depends on the `DataFetcher` type, how results are returned, and the configured executor/runtime. A synchronous resolver performing blocking work can still stall execution. If a service supports async or reactive execution, use the appropriate return type rather than spawning ad-hoc threads in controllers.

The key contract rule is **do not rely on execution order among query root fields**. For example, never write a `reserveInventory` field in `Query` and expect a subsequent `bookById` field to run after it and observe updated data. Queries should represent read operations without side effects. Root fields of a mutation are executed sequentially by GraphQL and are appropriate for data-modifying operations.

## 8. Distinguishing Query and Mutation with Multiple Fields

A mutation can contain multiple root fields:

```graphql
type Mutation {
    updateBookTitle(id: ID!, title: String!): Book!
    publishBook(id: ID!): Book!
}
```

```graphql
mutation UpdateAndPublish($id: ID!, $title: String!) {
    update: updateBookTitle(id: $id, title: $title) {
        id
        title
    }
    publish: publishBook(id: $id) {
        id
        title
    }
}
```

The root fields of a mutation are executed sequentially in the order they appear in the operation. Thus, `publishBook` executes after `updateBookTitle`. This sequential rule applies to mutation root fields; child fields inside their selection sets still follow normal field execution rules.

Queries are different: root fields carry no ordering guarantee. If two operations have data dependencies or side effects, model them as mutations and place them in the same operation when appropriate.

## 9. Handling Errors When One of Multiple Fields Fails

GraphQL can return successful data for some fields alongside a list of errors for other fields. For example, `bookById` returns valid data, `authorById` encounters a service error, and `latestBooks` still returns results.

The response may look like:

```json
{
  "data": {
    "bookById": {
      "id": "book-01",
      "title": "Spring in Action"
    },
    "authorById": null,
    "latestBooks": []
  },
  "errors": [
    {
      "message": "Author service is unavailable",
      "path": ["authorById"]
    }
  ]
}
```

This illustrates nullable fields. If a field is non-null and its resolver returns `null` due to an error, GraphQL applies null propagation up to the nearest nullable parent. Consequently, an error in one field can turn a larger portion of the response into `null`, depending on non-null placement in the schema.

Spring for GraphQL allows translating exceptions into GraphQL errors using `DataFetcherExceptionResolver`. Return messages appropriate for clients and keep sensitive technical details in server logs. Clients should inspect both `data` and `errors`; never assume a successful HTTP response means every field succeeded.

## 10. Optimizing Multiple Fields with DataLoader

Multiple root fields and nested fields in the same operation can request related data. For example, a query fetches 20 books and each book requests `author`. If the `Book.author` resolver executes a separate query per book, the request can trigger the N+1 problem.

GraphQL Java's DataLoader batches data fetches together and caches results within the request scope. Spring for GraphQL integrates `BatchLoaderRegistry` and also provides `@BatchMapping` for the common case:

```java
@Controller
public class BookAuthorController {

    private final AuthorService authorService;

    public BookAuthorController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> authors(List<Book> books) {
        Set<String> ids = books.stream()
            .map(Book::authorId)
            .collect(Collectors.toSet());

        Map<String, Author> authorsById = authorService.findAllByIds(ids);
        Map<Book, Author> result = new HashMap<>();
        for (Book book : books) {
            result.put(book, authorsById.get(book.authorId()));
        }
        return result;
    }
}
```

`Book.author` resolutions can be grouped so the service loads authors in bulk. If multiple root fields in the same request also share a DataLoader with the same keys, they can benefit from per-request caching and batch dispatch. Loaders must be request-scoped so data is never shared across users.

DataLoader does not replace good query design. Clients can still request a huge list or an overly deep selection set. Cap page sizes, set default/max limits, and consider query depth or complexity limits.

## 11. Multiple Fields and Server-Side Performance

A single request does not mean execution cost is always small. An operation can include many root fields, multiple aliases of the same field, multiple fragments, and deep selection sets. Each branch can trigger additional service calls, database queries, or external data fetches.

Measures to consider:

- Paginate lists and enforce maximum bounds on `first`, `limit`, or `pageSize`.
- Use DataLoader or `@BatchMapping` for repeated relationships to reduce N+1 queries.
- Use async/reactive execution when I/O can run asynchronously and the stack supports it.
- Measure per-field timing using instrumentation/observation to spot slow resolvers.
- Limit depth and complexity, especially for queries with many aliases or nested relationships.
- Enforce authorization on every sensitive field, even when multiple fields are combined in one operation.

Aliases can generate many response keys pointing to the same resolver. For example, a client could call `bookById` dozens of times with different IDs in one operation. This is convenient for clients, yet it can generate heavy load. The server needs complexity or call-count limits suited to system requirements.

## 12. Testing Queries with Multiple Fields Using GraphQlTester

`GraphQlTester` lets you send an operation containing multiple root fields and assert each branch in the response:

```java
graphQlTester.document("""
        query Dashboard($bookId: ID!, $authorId: ID!) {
            bookById(id: $bookId) {
                title
            }
            authorById(id: $authorId) {
                name
            }
            latestBooks(limit: 3) {
                id
            }
        }
        """)
    .variable("bookId", "book-01")
    .variable("authorId", "author-01")
    .execute()
    .path("bookById.title")
    .entity(String.class)
    .isEqualTo("Spring in Action");
```

You can also verify `authorById.name` and `latestBooks[*].id` using the appropriate assertion APIs. Things to test:

- All root fields return data together in one operation.
- Aliases allow calling the same field with different arguments.
- Variables are bound properly and default values work.
- Field conflicts are caught before resolvers run.
- One failing field preserves other fields' data when nullability permits.
- Mutation root fields execute sequentially.
- DataLoader batches data fetches and does not leak cache entries across requests.

In particular, when testing a single-field failure, verify both `errors` and the remaining `data` to ensure clients receive the partial response as designed.

## 13. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Calling the same field twice causes a field conflict | Same response key with incompatible arguments or selections | Use distinct aliases or merge selection sets |
| Response has only one key for the field | GraphQL uses the field name as the response key without an alias | Add aliases if multiple results must be distinguished |
| Resolver does not run | Field is not declared on `Query` or mapping name is wrong | Check the SDL and `@QueryMapping` |
| Resolver depends on field order | Query root fields have no sequential execution guarantee | Keep fields independent or move writes to a mutation |
| One failing field turns other data null | Non-null propagation bubbles through the parent | Review nullability and error handling per contract |
| One request with many aliases causes high load | Each response key can trigger a separate resolution | Limit complexity, alias count, and pagination |
| Multiple nested fields cause N+1 | Resolver loads relationships per source object | Use DataLoader or `@BatchMapping` |
| Multiple operations written but server runs only one | Request selects an operation via `operationName` | Send operations individually or combine root fields into one operation |

When debugging, first verify whether the query passed parsing and validation. If validation fails, check aliases, arguments, fragments, and response keys. If the operation is valid but data is missing, check resolvers, nullability, and `errors`. If the data is correct but slow, measure field-level latency, query counts, and selection set size.

## 14. Principles for Designing Queries with Multiple Fields

Group independent fields needed by a screen or use case into a single query to reduce round trips. Use aliases when the same field must be called with different arguments. Use variables to separate inputs from the document and fragments to reuse selection sets.

Keep query fields read-only and independent of execution order. Use mutations for state-changing operations that require deterministic ordering. Design nullability intentionally so a single failing field does not wipe out unrelated data. Use DataLoader for repeated relationships along with pagination and complexity limits to control server-side costs.

In Spring for GraphQL, each root field connects to a resolver via `@QueryMapping`, while nested fields use `@SchemaMapping` or `@BatchMapping`. GraphQL Java handles collecting, validating, and executing fields in the operation; Spring provides the wiring to controllers, services, context, and DataLoader. Understanding these rules helps build multi-field queries that are convenient, efficient, and predictable.
