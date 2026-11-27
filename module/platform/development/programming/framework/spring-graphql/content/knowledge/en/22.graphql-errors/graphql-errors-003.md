# DataFetchingEnvironment

## Objectives

After this lesson, you will be able to:

- Explain the role of `DataFetchingEnvironment` during the execution of a GraphQL field.
- Read arguments, source objects, `GraphQLContext`, local context, and current field information.
- Use the selection set to inspect which child fields the client requested.
- Access the execution path and metadata needed to construct accurate GraphQL errors.
- Combine `DataFetchingEnvironment` with `DataFetcherExceptionResolver` and `DataFetcherResult`.
- Access DataLoader when working directly with GraphQL Java.
- Know when to use `DataFetchingEnvironment` and when to prefer `@Argument`, a source parameter, or `@ContextValue`.

## 1. What is DataFetchingEnvironment?

`DataFetchingEnvironment` is the GraphQL Java object provided to a DataFetcher when GraphQL is resolving a field. It holds the data and metadata for the current field execution.

A field resolver typically needs one or more pieces of information:

- Arguments passed by the client to the field.
- The source object returned by the parent field.
- The request's `GraphQLContext`.
- Local context passed down from the parent field.
- The field name, field definition, and execution path.
- Child fields selected by the client.
- The DataLoader registry and certain operation metadata.

This information is gathered in `DataFetchingEnvironment` so that the DataFetcher can fetch the right data for the current execution context.

For example, a client sends the query:

~~~graphql
query BookDetail($id: ID!) {
  book(id: $id) {
    id
    title
    author {
      name
    }
  }
}
~~~

When the `Query.book` field runs, the environment contains the `id` argument. After the parent field returns a `Book`, the resolver for `Book.author` receives that `Book` as its source object. Each field has its own environment, reflecting its corresponding field and execution branch.

You can visualize it as:

~~~mermaid
flowchart TD
    A[GraphQL operation] --> B[Query.book]
    B --> C[DataFetchingEnvironment]
    C --> D[Arguments]
    C --> E[GraphQLContext]
    C --> F[Field and execution path]
    C --> G[Selection set]
    B --> H[Book source object]
    H --> I[Book.author]
    I --> J[Author DataFetchingEnvironment]
    J --> K[Source = Book]
    J --> L[Arguments / context / path]
~~~

`DataFetchingEnvironment` is an API at the GraphQL Java layer. Spring for GraphQL allows methods in an annotated controller to accept this object when they need more detailed metadata than specialized annotations provide.

## 2. Receiving DataFetchingEnvironment in an annotated controller

A method annotated with `@QueryMapping` or `@SchemaMapping` can accept `DataFetchingEnvironment` as a parameter.

Example SDL:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

Controller:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(DataFetchingEnvironment environment) {
        String id = environment.getArgument("id");
        return bookService.findById(id);
    }
}
~~~

Spring recognizes the `DataFetchingEnvironment` parameter and supplies the environment for the field being invoked. The method reads the `id` argument using `getArgument("id")` and then passes the data to the service.

For a simple argument, a shorter style is usually preferred:

~~~java
@QueryMapping
public Book book(@Argument String id) {
    return bookService.findById(id);
}
~~~

Prefer `@Argument` when you only need to bind a value. Use `DataFetchingEnvironment` when the resolver needs additional information such as field path, selection set, GraphQLContext, or source object.

## 3. Reading field arguments

`getArgument(name)` retrieves the argument value of the current field after GraphQL has parsed and coerced it according to the schema.

For example:

~~~graphql
type Query {
  searchBooks(keyword: String!, first: Int = 20): [Book!]!
}
~~~

DataFetcher:

~~~java
DataFetcher<List<Book>> searchBooksFetcher = environment -> {
    String keyword = environment.getArgument("keyword");
    Integer first = environment.getArgument("first");

    return bookService.search(keyword, first);
};
~~~

Related APIs:

| API | Meaning |
|---|---|
| `getArgument("name")` | Get a single argument by name |
| `getArguments()` | Get a map of all arguments for the field |
| `containsArgument("name")` | Check whether an argument was provided |
| `getVariables()` | Get operation variables |

GraphQL validates argument types against the SDL before invoking the DataFetcher. For example, if `first` is declared as `Int`, an invalid type can be rejected at the coercion step before the resolver runs.

### Distinguishing omitted and explicit null

For a nullable argument, a client can omit the argument or explicitly pass `null`. These two states can have different meanings in a partial update mutation.

`containsArgument("subtitle")` checks whether the key is present in the argument map after coercion. If the schema declares a default value, keep in mind that the default value may have been applied even when the client did not send the argument. When you need to accurately distinguish omitted from explicit null in an annotated controller, `ArgumentValue<T>` is a clearer choice.

~~~java
@MutationMapping
public Book updateSubtitle(
        @Argument String id,
        @Argument ArgumentValue<String> subtitle) {

    if (subtitle.isOmitted()) {
        return bookService.findById(id);
    }

    return bookService.updateSubtitle(id, subtitle.value());
}
~~~

Do not assume that every Java null value has the same meaning. Design the input contract and resolver according to the exact update semantics.

## 4. Reading the current field's source object

The source object is the value returned by the parent field and passed as input to the child field. In `DataFetchingEnvironment`, you can retrieve it with `getSource()`.

SDL:

~~~graphql
type Book {
  id: ID!
  author: Author
}

type Author {
  id: ID!
  name: String!
}
~~~

DataFetcher for `Book.author`:

~~~java
DataFetcher<Author> authorFetcher = environment -> {
    Book book = environment.getSource();
    return authorService.findById(book.getAuthorId());
};
~~~

In an annotated controller, you can receive the source object directly:

~~~java
@SchemaMapping
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

Receiving the source via a strongly typed parameter is usually easier to read and more type-safe. `getSource()` is useful when working directly with a DataFetcher or when reading the source alongside other metadata in the same method.

The source object is not an argument. For the `Book.author` field, the source is `Book`; arguments, if any, would be data the client passes directly to the `author` field itself.

## 5. GraphQLContext and local context

The environment provides two types of context with different scopes.

### GraphQLContext

`getGraphQlContext()` returns the shared context of the GraphQL request. This context is suited for metadata shared across operation execution, such as:

- Correlation ID or request ID.
- Authenticated tenant.
- Principal information or permissions determined at the security layer.
- Locale or metadata for logging.

For example:

~~~java
@QueryMapping
public List<Book> myBooks(DataFetchingEnvironment environment) {
    GraphQLContext context = environment.getGraphQlContext();
    String tenantId = context.get("tenantId");

    return bookService.findByTenant(tenantId);
}
~~~

The `tenantId` value should be placed into `GraphQLContext` by a trusted component such as an interceptor or security integration. Do not take an arbitrary tenant or user ID from an argument and use it as an authorization boundary.

In an annotated controller, you can use `@ContextValue` if you only need a single context value:

~~~java
@QueryMapping
public List<Book> myBooks(
        @ContextValue("tenantId") String tenantId) {
    return bookService.findByTenant(tenantId);
}
~~~

### Local context

`getLocalContext()` reads context passed down from a parent field to its child fields. Local context is suited for data that is only meaningful within one branch of the execution tree.

A DataFetcher can return `DataFetcherResult` and attach local context:

~~~java
DataFetcher<DataFetcherResult<Book>> bookFetcher = environment -> {
    Book book = bookService.findById(
            environment.getArgument("id"));

    Map<String, Object> local = Map.of(
            "includeInternalMetadata", false);

    return DataFetcherResult.<Book>newResult()
            .data(book)
            .localContext(local)
            .build();
};
~~~

A child field can read the local context:

~~~java
DataFetcher<String> internalLabelFetcher = environment -> {
    Map<String, Object> local = environment.getLocalContext();

    boolean allowed = Boolean.TRUE.equals(
            local.get("includeInternalMetadata"));

    return allowed ? "Internal" : "Public";
};
~~~

This example only illustrates the mechanism of passing data down a branch. Local context is not an authorization mechanism replacing Spring Security; data access permissions must still be checked at the appropriate layer.

| Data type | Scope | API |
|---|---|---|
| Source object | Parent object of the current field | `getSource()` |
| GraphQLContext | Entire GraphQL request | `getGraphQlContext()` |
| Local context | Parent-child branch passed intentionally | `getLocalContext()` |
| Argument | Current field | `getArgument(...)` |

Avoid using shared mutable context to store per-field state. If data is only meant for a single branch, local context expresses that scope more clearly.

## 6. Reading field information and execution path

`DataFetchingEnvironment` provides information about the field currently being executed and its position in the response.

Commonly used APIs:

| API | Content |
|---|---|
| `getField()` | Field node in the GraphQL document |
| `getFieldDefinition()` | Field definition in the schema |
| `getExecutionStepInfo()` | Current execution step information |
| `getExecutionStepInfo().getPath()` | Field path in the response |
| `getMergedField()` | Merged fields information for the same response key |
| `getOperationDefinition()` | Operation definition |
| `getExecutionId()` | ID of the execution |

Example of retrieving field name, alias, and path:

~~~java
DataFetcher<Book> bookFetcher = environment -> {
    String fieldName = environment.getField().getName();
    String alias = environment.getField().getAlias();
    String path = environment.getExecutionStepInfo()
            .getPath()
            .toString();

    log.debug(
            "Resolving field={}, alias={}, path={}",
            fieldName, alias, path);

    return bookService.findById(
            environment.getArgument("id"));
};
~~~

If the client uses an alias:

~~~graphql
query {
  featured: book(id: "b-01") {
    title
  }
}
~~~

The field name in the schema is still `book`, while the response key is `featured`. The execution path reflects the position in the response and may include aliases or list indices. This is useful when logging or attaching errors to the exact field.

Do not use field names or paths to make access control decisions. They are operation metadata, not identity or proof that the user is allowed to read the data.

## 7. Using the selection set to inspect requested child fields

`getSelectionSet()` returns a `DataFetchingFieldSelectionSet`, allowing the resolver to see which child fields the client selected.

For example:

~~~graphql
query {
  book(id: "b-01") {
    id
    title
    author {
      name
    }
  }
}
~~~

Resolver:

~~~java
@QueryMapping
public Book book(DataFetchingEnvironment environment) {
    String id = environment.getArgument("id");

    DataFetchingFieldSelectionSet selectionSet =
            environment.getSelectionSet();

    boolean authorRequested =
            selectionSet.contains("author");

    return bookService.findForGraphQl(id, authorRequested);
}
~~~

The selection set can help optimize projections or decide whether to load an expensive relationship. However, it is only a signal of the response shape the client requested.

When using the selection set, keep in mind:

- Queries can contain fragments and inline fragments.
- Aliases can change response keys.
- A field can be requested across multiple branches.
- A field can have nested sub-selections.
- Directives such as `@skip` and `@include` affect which fields are executed.

The selection set should not be used as a hand-rolled parser replacing the GraphQL engine. Use the built-in selection set APIs and test with fragments, aliases, and directives.

Also, do not skip permission checks just because a client did not request a field in a given query. Authorization must be enforced whenever a sensitive field is executed.

## 8. Accessing DataLoader from the environment

In an annotated controller, Spring can inject `DataLoader` directly into a method parameter. When writing a DataFetcher manually, you can obtain the loader from the environment.

For example, assuming a DataLoader is registered under the name `authorLoader`:

~~~java
DataFetcher<CompletableFuture<Author>> authorFetcher = environment -> {
    Book book = environment.getSource();
    DataLoader<Long, Author> loader =
            environment.getDataLoader("authorLoader");

    return loader.load(book.getAuthorId());
};
~~~

`getDataLoader(name)` retrieves the DataLoader registered for the current request. `load(key)` queues the key so that DataLoader can batch multiple requests and invoke the batch loader.

Do not create a singleton DataLoader and share it across multiple requests. Spring for GraphQL integrates `BatchLoaderRegistry` to register DataLoaders per GraphQL request, keeping caching and batching properly scoped.

If using an annotated controller, the following approach is usually simpler:

~~~java
@SchemaMapping
public CompletableFuture<Author> author(
        Book book,
        DataLoader<Long, Author> authorLoader) {
    return authorLoader.load(book.getAuthorId());
}
~~~

Only use `DataFetchingEnvironment` to fetch a DataLoader when working directly with a DataFetcher or when the method already needs the environment for other metadata.

## 9. DataFetchingEnvironment in GraphQL error handling

A very useful aspect of `DataFetchingEnvironment` is that it supplies the field execution location to construct accurate GraphQL errors.

A GraphQL response can contain both `data` and `errors`. When a field raises an error, the error typically needs:

- A client-appropriate message.
- An error classification or error code.
- A path indicating the failing field.
- Source locations in the GraphQL document if available.
- Extensions containing necessary public metadata.

GraphQL Java provides `GraphqlErrorBuilder.newError(environment)` to build an error tied to the current field's environment.

For example:

~~~java
DataFetcher<Book> bookFetcher = environment -> {
    String id = environment.getArgument("id");
    Book book = bookService.findById(id);

    if (book == null) {
        throw new BookNotFoundException(id);
    }

    return book;
};
~~~

You can use Spring for GraphQL's `DataFetcherExceptionResolver` to convert exceptions into GraphQL errors:

~~~java
@Component
public class BookExceptionResolver
        extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable exception,
            DataFetchingEnvironment environment) {

        if (exception instanceof BookNotFoundException) {
            return GraphqlErrorBuilder.newError(environment)
                    .message("Book was not found")
                    .errorType(ErrorType.NOT_FOUND)
                    .extensions(Map.of(
                            "code", "BOOK_NOT_FOUND"))
                    .build();
        }

        return null;
    }
}
~~~

`GraphqlErrorBuilder.newError(environment)` uses the current field's metadata to attach the appropriate path and source location. As a result, clients can tell which branch of the response encountered the error.

Illustrative response example:

~~~json
{
  "data": {
    "book": null
  },
  "errors": [
    {
      "message": "Book was not found",
      "path": ["book"],
      "extensions": {
        "classification": "NOT_FOUND",
        "code": "BOOK_NOT_FOUND"
      }
    }
  ]
}
~~~

The exact structure of `extensions` depends on the error classification and application configuration. Only include metadata that clients need for handling; do not send SQL, stack traces, tokens, or internal information.

## 10. Distinguishing request errors and field resolution errors

Not every GraphQL error has a `DataFetchingEnvironment`.

| Error group | Timing | Has DataFetcher run? | Example |
|---|---|---:|---|
| Parse error | Document parsing | No | Missing bracket or syntax error |
| Validation error | Validating query against schema | No | Non-existent field, wrong argument type |
| Variable coercion error | Converting variables | No | Passing a string to an Int variable |
| Data fetching error | Field execution | Yes | Repository failure, insufficient permissions |
| Serialization error | Converting field value to response | Field has resolved | Value cannot be serialized by scalar |

`DataFetcherExceptionResolver` handles exceptions raised during data fetching. It does not replace parse error or validation error handling because those errors occur before any DataFetcher is invoked.

This helps choose the right handling layer:

- Syntax and schema contract errors are reported by the GraphQL engine before execution.
- Coercion errors are handled by scalars and GraphQL validation.
- Business or data access errors are handled in resolvers, services, and exception resolvers.
- Serialization errors require checking return data types and custom scalars.

## 11. DataFetcherResult: returning partial data with errors

There are cases where a resolver still has the primary data, but a piece of secondary information could not be loaded. If the schema and business rules allow, you can return `DataFetcherResult` to provide data together with errors and local context.

For example:

~~~java
DataFetcher<DataFetcherResult<Book>> bookFetcher = environment -> {
    String id = environment.getArgument("id");
    Book book = bookService.findById(id);

    if (book == null) {
        GraphQLError error = GraphqlErrorBuilder.newError(environment)
                .message("Book was not found")
                .errorType(ErrorType.NOT_FOUND)
                .build();

        return DataFetcherResult.<Book>newResult()
                .data(null)
                .error(error)
                .build();
    }

    return DataFetcherResult.<Book>newResult()
            .data(book)
            .build();
};
~~~

`DataFetcherResult` can carry:

- `data`: the field value.
- `errors`: one or more GraphQL errors.
- `localContext`: context passed down to child fields.

This approach is suitable when a resolver needs explicit control over a partial result. If you only need to turn an exception into a GraphQL error, `DataFetcherExceptionResolver` is usually easier to manage.

Do not use partial data to hide errors that compromise business integrity. Define clearly which fields can be independently missing and which must fail together.

## 12. Using DataFetchingEnvironment with reactive DataFetchers

Spring for GraphQL supports DataFetchers returning `Mono` and `Flux`. When using a reactive pipeline, extract the needed values from the environment before constructing the publisher.

For example:

~~~java
DataFetcher<Mono<Book>> bookFetcher = environment -> {
    String id = environment.getArgument("id");
    GraphQLContext context = environment.getGraphQlContext();
    String tenantId = context.get("tenantId");

    return bookService.findByIdAndTenant(id, tenantId);
};
~~~

Extract the required values before entering the pipeline and pass strongly typed data to the service. Avoid storing the entire `DataFetchingEnvironment` in a mutable field or keeping it for use after the operation completes.

Example with an annotated controller:

~~~java
@QueryMapping
public Mono<Book> book(DataFetchingEnvironment environment) {
    String id = environment.getArgument("id");
    String tenantId = environment.getGraphQlContext()
            .get("tenantId");

    return bookService.findByIdAndTenant(id, tenantId);
}
~~~

Do not call `block()` or `subscribe()` inside a resolver. Return the publisher so Spring for GraphQL can manage execution and convert the result into a GraphQL response.

## 13. Common pitfalls when using DataFetchingEnvironment

| Symptom | Possible cause | Solution |
|---|---|---|
| `getArgument` returns null | Wrong argument name or argument was omitted | Cross-check the SDL and check presence |
| Source object has wrong type | Parent field returned an unexpected DTO | Check the return type of the parent resolver |
| Context is missing key | Interceptor has not added metadata to GraphQLContext | Check the context initialization step |
| Misused local context | Confusing request-wide context with branch-scoped context | Choose `getGraphQlContext` or `getLocalContext` appropriately |
| Error lacks proper path | Manually building GraphQLError without attaching environment | Use `GraphqlErrorBuilder.newError(environment)` |
| Selection set misses a field | Not accounting for fragments, aliases, or directives | Use the selection set APIs and test complex queries |
| User data leaks across requests | Storing environment or context in shared mutable state | Keep data scoped to the request and reactive chain |
| Resolver overly coupled to GraphQL Java | Passing environment down into service/domain layers | Extract arguments/context into specific inputs |

## 14. Principles for using DataFetchingEnvironment

`DataFetchingEnvironment` is a powerful tool, but not every method needs to accept it.

Use it when:

- You need to read multiple arguments or check argument presence.
- You need the source object in a manual DataFetcher.
- You need `GraphQLContext` or local context.
- You need the selection set to optimize queries.
- You need field path, alias, or execution metadata.
- You need to build a GraphQL error tied to a specific field.
- You need to obtain a DataLoader from the environment.

Prefer Spring abstractions when:

- Only a single argument is needed: use `@Argument`.
- You need the source object in a controller: accept a strongly typed Java parameter.
- Only a single context value is needed: use `@ContextValue`.
- You need batch loading for relationships: use `@BatchMapping` or DataLoader.
- You need exception handling: use `DataFetcherExceptionResolver`.

Do not pass `DataFetchingEnvironment` across the service and domain layers. Extract the required data at the GraphQL boundary, convert it into clearly typed parameters or commands, and then call the service.

## 15. Testing DataFetchingEnvironment and error mapping

You can use `GraphQlTester` to test resolvers and error responses against the actual schema.

Example testing a missing field:

~~~java
@Test
void shouldReturnNotFoundErrorForMissingBook() {
    graphQlTester.document("""
            query {
                book(id: "missing") {
                    id
                    title
                }
            }
            """)
            .execute()
            .errors()
            .satisfy(errors -> {
                assertThat(errors).isNotEmpty();
                assertThat(errors.get(0).getMessage())
                        .isEqualTo("Book was not found");
                assertThat(errors.get(0).getPath())
                        .containsExactly("book");
            });
}
~~~

Scenarios to test:

1. Arguments are read correctly from the environment.
2. Source objects are passed properly to child fields.
3. `GraphQLContext` and local context have the right scope.
4. Aliases are accurately reflected in the execution path.
5. The selection set detects fields selected through fragments.
6. DataLoaders are retrieved properly and batch functions work.
7. Exception resolvers produce errors with appropriate message, classification, and path.
8. Parse/validation errors are not confused with data fetching errors.
9. `DataFetcherResult` returns partial data and errors per the contract.
10. Reactive resolvers do not block and handle empty/error publishers according to nullability.

Verify both response contents and error paths/extensions. Checking only the message is not enough to guarantee that clients can pinpoint the failing field.

## Conclusion

`DataFetchingEnvironment` is the per-field context during GraphQL execution. It provides arguments, source objects, `GraphQLContext`, local context, the selection set, field definitions, and the execution path. In Spring for GraphQL, annotated controllers can accept the environment directly when this information is needed.

Especially in error handling, the environment enables `GraphqlErrorBuilder.newError(environment)` to tie errors to the exact field and path. Combined with `DataFetcherExceptionResolver` or `DataFetcherResult`, the server can return clear errors and partial data when appropriate. Use the environment at the GraphQL boundary, extract the required data, and pass it to services to keep the business layer independent and easy to test.

## References

- [Spring for GraphQL — Request Execution and Error Handling](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Exception Resolution](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution.exceptions)
- [GraphQL Java — DataFetchingEnvironment API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/schema/DataFetchingEnvironment.html)
- [GraphQL Java — DataFetcherResult API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/execution/DataFetcherResult.html)
