# Custom DataFetcher

In Spring for GraphQL, every field in a GraphQL schema needs a way to retrieve its value when queried by a client. GraphQL Java delegates that responsibility to a `DataFetcher`. A data fetcher can read data from a repository, invoke an application service, compute a value from a parent object, or combine multiple data sources to return a value for the field.

Spring for GraphQL generally recommends using `@QueryMapping`, `@MutationMapping`, and `@SchemaMapping` in controllers because they integrate well with dependency injection, argument binding, and Spring mechanisms. However, there are cases where you need to register a `DataFetcher` directly—such as integrating an existing GraphQL Java resolver, customizing a special field, or using a GraphQL Java API that controller annotations cannot express conveniently.

This lesson explains how to build a `DataFetcher`, read `DataFetchingEnvironment`, register a field using `RuntimeWiringConfigurer`, handle errors, pass local context, integrate DataLoader, and write tests.

## 1. Where Does DataFetcher Fit in Execution?

A GraphQL schema describes the types and fields a client can request. When GraphQL Java executes an operation, it invokes the `DataFetcher` attached to each field to obtain its runtime value.

~~~mermaid
flowchart TD
    A[GraphQL document] --> B[Validate against schema]
    B --> C[Execute selected field]
    C --> D[Invoke DataFetcher]
    D --> E[Read arguments and context]
    E --> F[Call service or repository]
    F --> G[Return value]
    G --> H[Complete child fields]
    H --> I[Build GraphQL response]
~~~

Example schema:

~~~graphql
type Query {
    books(term: String!, limit: Int = 20): [Book!]!
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

The `Query.books` field needs to retrieve a list of books based on a search term and a limit. The `Book.title` field may simply read the `title` property from the `Book` object returned by its parent field. Both fields have a data fetcher, but they retrieve data differently.

GraphQL Java typically uses `PropertyDataFetcher` as the default data fetcher to read properties from the source object. Therefore, not every field requires a dedicated resolver. Only create a custom `DataFetcher` when you need to query data, apply business logic, call external services, or transform data.

## 2. The DataFetcher Contract

`DataFetcher<T>` is a GraphQL Java interface with one primary method:

~~~java
public interface DataFetcher<T> {
    T get(DataFetchingEnvironment environment) throws Exception;
}
~~~

The generic `T` represents the type of value the data fetcher returns. That value can be a single object, a collection, a `CompletionStage`, a configured reactive publisher, or a `DataFetcherResult`.

The `get` method receives a `DataFetchingEnvironment`, which holds information about the current field resolution. A data fetcher does not need to parse the GraphQL document itself to find arguments or the executing field.

A data fetcher should have the following characteristics:

- Perform only the work required to resolve the field.
- Receive dependencies via constructor or Spring dependency injection.
- Do not store request-specific data in instance fields.
- Do not create a `GraphQL` instance or re-execute the document itself.
- Return a data type compatible with the field type in the schema.

If a data fetcher throws an exception, GraphQL Java passes the exception through the configured `DataFetcherExceptionHandler`. Spring for GraphQL can combine `DataFetcherExceptionResolver` instances to convert exceptions into GraphQL errors.

## 3. What Does DataFetchingEnvironment Provide?

`DataFetchingEnvironment` is the main entry point for a custom data fetcher. Some commonly used methods:

| Method | Purpose |
| --- | --- |
| `getArgument(name)` | Read a field argument |
| `containsArgument(name)` | Check whether an argument was provided |
| `getSource()` | Get the parent object being resolved |
| `getGraphQlContext()` | Read shared context across the GraphQL execution |
| `getLocalContext()` | Read context passed down from the parent field |
| `getField()` | Get information about the current field |
| `getExecutionStepInfo()` | Get position and type info for the execution step |
| `getSelectionSet()` | Inspect the requested child fields |
| `getLocale()` | Get the execution locale |
| `getDataLoader(name)` | Retrieve a registered DataLoader |

Example of reading arguments:

~~~java
String term = environment.getArgument("term");
Integer limit = environment.getArgument("limit");
~~~

`getArgument` is a generic method. Assign the result to a type matching the GraphQL schema and check for null when the argument can be absent or has a default value.

You can use `containsArgument` when you need to distinguish between a client omitting an argument and a client sending `null`:

~~~java
if (environment.containsArgument("limit")) {
    Integer requestedLimit = environment.getArgument("limit");
    // Apply the requested value according to the API contract.
}
~~~

You should not read raw variables directly and re-bind them manually. GraphQL Java already performs parsing, validation, and argument coercion according to the schema before invoking the data fetcher.

## 4. Writing a Custom DataFetcher for Query.books

Suppose an application service has a method for searching books:

~~~java
package com.example.books.application;

import java.util.List;
import java.util.Optional;

public interface BookCatalogService {
    List<BookView> search(String term, int limit);
    Optional<BookView> findById(String id);
}
~~~

Create a dedicated data fetcher:

~~~java
package com.example.books.graphql;

import java.util.List;

import com.example.books.application.BookCatalogService;
import com.example.books.application.BookView;

import graphql.schema.DataFetcher;
import graphql.schema.DataFetchingEnvironment;

import org.springframework.stereotype.Component;

@Component
public class BookSearchDataFetcher implements DataFetcher<List<BookView>> {

    private final BookCatalogService catalogService;

    public BookSearchDataFetcher(BookCatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @Override
    public List<BookView> get(DataFetchingEnvironment environment) {
        String term = environment.getArgument("term");
        Integer requestedLimit = environment.getArgument("limit");

        int limit = requestedLimit == null
            ? 20
            : Math.min(Math.max(requestedLimit, 1), 100);

        return catalogService.search(term, limit);
    }
}
~~~

The data fetcher uses constructor injection to receive the service. It applies a default limit of 20 and clamps the client-requested value between 1 and 100. This limit protects the backend from overly large queries; in a real application, align this limit with the API's pagination policy.

Do not store `term`, `limit`, or `DataFetchingEnvironment` in fields of `BookSearchDataFetcher`. Spring-managed beans typically have singleton scope, and multiple requests can execute concurrently on the same instance. Request data must stay in local variables of the `get` invocation.

## 5. Registering a DataFetcher with RuntimeWiringConfigurer

GraphQL Java binds a data fetcher to a specific field in the schema. In Spring for GraphQL, `RuntimeWiringConfigurer` allows customizing `RuntimeWiring.Builder`.

~~~java
package com.example.books.graphql;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class BookGraphQlConfiguration {

    @Bean
    RuntimeWiringConfigurer bookSearchConfigurer(
            BookSearchDataFetcher bookSearchDataFetcher) {

        return wiringBuilder -> wiringBuilder.type(
            "Query",
            typeBuilder -> typeBuilder.dataFetcher(
                "books",
                bookSearchDataFetcher
            )
        );
    }
}
~~~

The configuration above registers `BookSearchDataFetcher` for the field coordinate `Query.books`. The type and field names must match the loaded SDL schema.

With the Spring Boot GraphQL starter, beans of type `RuntimeWiringConfigurer` are automatically detected and applied to `GraphQlSource.Builder`. You usually do not need to create `GraphQL` or `GraphQlSource` manually just to register a data fetcher.

If the application builds `GraphQlSource` manually without Boot auto-configuration, apply the configurer to the builder during schema/runtime wiring creation.

## 6. Choosing the Right Way to Register a Resolver

There are several ways to attach resolution logic to a field:

| Approach | When to Use |
| --- | --- |
| `@QueryMapping` | Query root field in a Spring controller |
| `@MutationMapping` | Mutation root field in a Spring controller |
| `@SubscriptionMapping` | Subscription root field |
| `@SchemaMapping` | Field on a GraphQL object type |
| `RuntimeWiringConfigurer` + `DataFetcher` | Direct GraphQL Java wiring is needed |
| `PropertyDataFetcher` | Field only reads a property from the source object |

Controller example:

~~~java
import com.example.books.application.BookCatalogService;
import com.example.books.application.BookNotFoundException;
import com.example.books.application.BookView;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private final BookCatalogService catalogService;

    public BookQueryController(BookCatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @QueryMapping
    public BookView book(@Argument String id) {
        return catalogService.findById(id)
            .orElseThrow(() -> new BookNotFoundException(id));
    }
}
~~~

Spring registers the `book` method as a data fetcher for the `Query.book` field. It is still a `DataFetcher` at the GraphQL Java layer, but Spring creates and manages the wiring from the annotation.

Do not register both `@QueryMapping` and `RuntimeWiringConfigurer` for the same `Query.book` coordinate. Having two mechanisms attempt to define a resolver for one field makes configuration confusing and dependent on registration order. Each field should have a single, clear wiring mechanism.

Use controller annotations as the default choice for regular resolvers. Choose `RuntimeWiringConfigurer` when you need direct control over GraphQL Java runtime wiring or want to reuse an existing `DataFetcher`.

## 7. Resolving Child Fields Using the Source Object

Data fetchers are not limited to root fields. For a field on a parent object, `environment.getSource()` returns the value provided by the parent field's data fetcher.

For example, the `Book.author` field needs to look up the author from the book's `authorId`:

~~~java
import com.example.books.application.AuthorService;
import com.example.books.application.AuthorView;
import com.example.books.application.BookView;

import graphql.schema.DataFetcher;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.stereotype.Component;

@Component
public class BookAuthorLookupDataFetcher implements DataFetcher<AuthorView> {

    private final AuthorService authorService;

    public BookAuthorLookupDataFetcher(AuthorService authorService) {
        this.authorService = authorService;
    }

    @Override
    public AuthorView get(DataFetchingEnvironment environment) {
        BookView book = environment.getSource();
        return authorService.findById(book.authorId());
    }
}
~~~

Registering the child field:

~~~java
@Bean
RuntimeWiringConfigurer bookAuthorConfigurer(
        BookAuthorLookupDataFetcher authorDataFetcher) {

    return builder -> builder.type(
        "Book",
        type -> type.dataFetcher("author", authorDataFetcher)
    );
}
~~~

In cases where the `author` field simply corresponds to an existing property on the source object, no custom data fetcher is needed. The default `PropertyDataFetcher` can read the matching getter or property. Only use a dedicated resolver when you need to query data, check permissions, transform values, or apply additional logic.

## 8. Using GraphQlContext for Request-Scoped Data

`DataFetchingEnvironment.getGraphQlContext()` provides a shared context across a single GraphQL execution. Applications can populate it with authenticated data or request metadata, such as the current tenant, correlation ID, or locale determined at the transport layer.

Example of a data fetcher reading the tenant from the GraphQL context:

~~~java
@Override
public List<BookView> get(DataFetchingEnvironment environment) {
    String tenantId = environment.getGraphQlContext().get("tenantId");
    String term = environment.getArgument("term");

    return catalogService.searchForTenant(tenantId, term);
}
~~~

The `tenantId` value must be set from a trusted source such as the authenticated principal or a request interceptor. Do not take a tenant ID passed by the client in an argument and treat it as an authenticated identity. The application service still needs to verify data access permissions according to the application's security policy.

The GraphQL context is shared across the execution. Do not use it to store mutable state shared among multiple parallel fields. If a parent field needs to pass private data down to its child fields, consider `localContext`.

## 9. Passing Data to Child Fields with Local Context

`DataFetcherResult` allows returning data along with local context, errors, or extensions. Local context is passed down to child field data fetchers via `getLocalContext()`.

For example, a parent field loads display policy information and wants child fields to reuse it:

~~~java
import graphql.execution.DataFetcherResult;
import graphql.schema.DataFetchingEnvironment;

@Override
public DataFetcherResult<BookView> get(DataFetchingEnvironment environment) {
    String id = environment.getArgument("id");
    BookView book = catalogService.findById(id)
        .orElseThrow(() -> new BookNotFoundException(id));

    BookViewPolicy policy = policyService.policyFor(book);

    return DataFetcherResult.<BookView>newResult()
        .data(book)
        .localContext(policy)
        .build();
}
~~~

The child field's data fetcher can read that context:

~~~java
@Override
public String get(DataFetchingEnvironment environment) {
    BookView book = environment.getSource();
    BookViewPolicy policy = environment.getLocalContext();

    return policy.canShowInternalCode()
        ? book.internalCode()
        : null;
}
~~~

Local context is scoped to the parent field's data branch, making it suitable for metadata that only needs to be passed down to child fields. It does not replace the execution-wide GraphQL context, nor should it hold mutable objects modified concurrently by multiple fields.

Use `DataFetcherResult` when you intentionally need to pass extra metadata. If you are only returning a regular object, return the object directly to keep the resolver simpler.

## 10. Returning Data and GraphQL Errors with DataFetcherResult

A data fetcher may sometimes return partial data while also adding errors to the response. `DataFetcherResult` supports that scenario:

~~~java
import graphql.execution.DataFetcherResult;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

@Override
public DataFetcherResult<BookView> get(DataFetchingEnvironment environment) {
    String id = environment.getArgument("id");
    BookView book = catalogService.findById(id).orElse(null);

    if (book == null) {
        return DataFetcherResult.<BookView>newResult()
            .data(null)
            .error(
                GraphqlErrorBuilder.newError(environment)
                    .message("Book not found")
                    .build()
            )
            .build();
    }

    return DataFetcherResult.<BookView>newResult()
        .data(book)
        .build();
}
~~~

`DataFetcherResult` is useful when a data fetcher needs to explicitly build a GraphQL error with the appropriate path or pass local context. It does not turn an error into a separate HTTP status code by itself; GraphQL still returns the response according to execution and transport rules.

Pay attention to nullability in the schema. If a field is declared non-null and the data fetcher returns null, GraphQL applies null propagation up to the parent according to the schema. Schema design and partial data return behavior must stay consistent with the API contract.

Do not use `DataFetcherResult` to hide technical exceptions. Database connection errors, system failures, or unexpected errors should be handled via exception resolvers and centralized logging.

## 11. Throwing Exceptions and Centralized Handling

A data fetcher can throw an exception instead of manually building a `DataFetcherResult`:

~~~java
@Override
public BookView get(DataFetchingEnvironment environment) {
    String id = environment.getArgument("id");

    return catalogService.findById(id)
        .orElseThrow(() -> new BookNotFoundException(id));
}
~~~

GraphQL Java routes exceptions thrown by data fetchers through an exception handler. For a custom `DataFetcher` that does not originate from an annotated controller, register a bean implementing `DataFetcherExceptionResolver`. `@GraphQlExceptionHandler` applies by default to controller invocations managed by `AnnotatedControllerConfigurer`. If you want to reuse annotated controller exception handlers for custom fetchers, retrieve the resolver from `AnnotatedControllerConfigurer` and register it with `GraphQlSource`.

Centralized resolver example:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

import org.springframework.graphql.execution.DataFetcherExceptionResolverAdapter;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.stereotype.Component;

@Component
public class BookExceptionResolver extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable exception,
            DataFetchingEnvironment environment) {

        if (exception instanceof BookNotFoundException) {
            return GraphqlErrorBuilder.newError(environment)
                .message("Book not found")
                .errorType(ErrorType.NOT_FOUND)
                .build();
        }

        return null;
    }
}
~~~

When a resolver does not handle an exception, return `null` so the next resolver in the chain has a chance to handle it. Do not return messages containing SQL, stack traces, tokens, or internal details to the client. Log detailed diagnostics on the server with an appropriate correlation ID.

Use an exception resolver for errors that need consistent translation across multiple fields. Use `DataFetcherResult` when a resolver intentionally returns partial data and error metadata as part of its result.

## 12. Asynchronous DataFetchers

GraphQL Java supports data fetchers returning `CompletionStage<T>`. This is useful when the application service already exposes an asynchronous API:

~~~java
import java.util.concurrent.CompletionStage;

import graphql.schema.DataFetcher;
import graphql.schema.DataFetchingEnvironment;

import org.springframework.stereotype.Component;

@Component
public class AsyncBookDataFetcher
        implements DataFetcher<CompletionStage<BookView>> {

    private final AsyncBookCatalogService catalogService;

    public AsyncBookDataFetcher(AsyncBookCatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @Override
    public CompletionStage<BookView> get(DataFetchingEnvironment environment) {
        String id = environment.getArgument("id");
        return catalogService.findById(id);
    }
}
~~~

GraphQL Java waits for the completion stage before completing the field and continuing to assemble the response. Let the service layer manage executors, timeouts, and asynchronous errors. Do not spawn a new thread per field or use `CompletableFuture.supplyAsync` with the common pool to wrap a blocking call without a resource management plan.

Spring for GraphQL configures `GraphQlSource` by default to support data fetchers returning Reactor `Mono` or `Flux`: for queries and mutations, reactive values are adapted so GraphQL Java handles them asynchronously; for subscriptions, the publisher is preserved to emit events. If you replace the builder or execution strategy manually, verify that reactive support remains enabled.

Do not mix blocking JDBC/JPA with a reactive pipeline simply by changing the return type. Choose the right programming model and avoid blocking event-loop threads.

## 13. Combining with DataLoader to Avoid N+1

A custom data fetcher that resolves a relationship field by calling a repository for each parent can trigger N+1 queries.

For example, a client requests the authors of many books. If every resolution of `Book.author` makes a separate database call, a single request can issue one query to fetch books and N queries to fetch authors.

DataLoader batches keys within the same execution into a single batch call. A data fetcher can retrieve the loader from the environment:

~~~java
import java.util.concurrent.CompletionStage;

import org.dataloader.DataLoader;
import graphql.schema.DataFetcher;
import graphql.schema.DataFetchingEnvironment;

import com.example.books.application.AuthorView;
import com.example.books.application.BookView;
import org.springframework.stereotype.Component;

@Component
public class BookAuthorDataFetcher
        implements DataFetcher<CompletionStage<AuthorView>> {

    @Override
    public CompletionStage<AuthorView> get(DataFetchingEnvironment environment) {
        BookView book = environment.getSource();

        DataLoader<String, AuthorView> authorLoader =
            environment.getDataLoader("authorById");

        return authorLoader.load(book.authorId());
    }
}
~~~

The DataLoader named `authorById` must be registered in the execution's `DataLoaderRegistry`. In a Spring for GraphQL application, you can integrate batch loaders via `BatchLoaderRegistry` or use `@BatchMapping` for suitable relationships.

DataLoaders typically cache per request/execution. Do not create a shared singleton loader across requests, as that can leak data or cache scopes across users/tenants. Loaders must be created and registered according to the lifecycle managed by Spring GraphQL.

Example of registering a loader in Spring Boot. Assume `AuthorService.findByIds` accepts a collection of IDs and returns `Mono<Map<String, AuthorView>>`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.BatchLoaderRegistry;
import com.example.books.application.AuthorService;
import com.example.books.application.AuthorView;

@Configuration
public class AuthorBatchConfiguration {

    public AuthorBatchConfiguration(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(String.class, AuthorView.class)
            .withName("authorById")
            .registerMappedBatchLoader((authorIds, environment) ->
                authorService.findByIds(authorIds)
            );
    }
}
~~~

`BatchLoaderRegistry` is a bean provided by the Spring Boot starter. The registered name `authorById` must match the name passed to `getDataLoader` by the custom data fetcher.

A custom `DataFetcher` should focus on resolving the field and calling the `DataLoader`. Batching logic, key-to-result mapping, and handling missing keys belong in the batch loader.

## 14. Security and Query Cost Control

A custom data fetcher is a backend execution entry point, so apply limits similar to regular APIs:

- Enforce access control in the application service or appropriate security layer.
- Obtain the principal/tenant from a trusted context; never trust IDs self-reported by the client.
- Cap page sizes, item counts, and input sizes.
- Do not log full arguments, tokens, or sensitive data.
- Use `DataLoader` or batch queries for relationship fields with N+1 risk.
- Avoid unnecessary network or database calls if a field is not requested.

`environment.getSelectionSet()` can help inspect the child fields requested by the client, but you should not turn the selection set into an authorization mechanism. Access rights must be enforced on the server for each relevant piece of data and operation.

GraphQL query complexity, depth limits, timeouts, and rate limits are complementary layers of defense. A custom `DataFetcher` does not replace request-level GraphQL safeguards.

## 15. Testing a Custom DataFetcher

You can unit test a data fetcher directly with Mockito without starting a GraphQL server. For example, verifying that the maximum limit is enforced before calling the service:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.example.books.application.BookCatalogService;
import com.example.books.application.BookView;

import graphql.schema.DataFetchingEnvironment;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class BookSearchDataFetcherTests {

    @Mock
    BookCatalogService catalogService;

    @Mock
    DataFetchingEnvironment environment;

    @InjectMocks
    BookSearchDataFetcher dataFetcher;

    @Test
    void capsRequestedLimitAtOneHundred() {
        when(environment.<String>getArgument("term")).thenReturn("spring");
        when(environment.<Integer>getArgument("limit")).thenReturn(500);
        when(catalogService.search("spring", 100)).thenReturn(List.of());

        List<BookView> result = dataFetcher.get(environment);

        assertThat(result).isEmpty();
        verify(catalogService).search("spring", 100);
    }
}
~~~

Unit tests verify the data fetcher's logic: reading the right arguments, applying defaults/limits, calling the service with appropriate parameters, and returning the expected result.

Add integration tests using `GraphQlTester` to verify that the field is registered at the right schema coordinate, arguments undergo proper GraphQL type coercion, the response has the right structure and nullability, exceptions are translated into expected GraphQL errors, and DataLoader is called in batches rather than once per parent.

Unit tests do not prove that `RuntimeWiringConfigurer` was discovered by Spring Boot. Only integration tests verify wiring from the schema all the way to the response.

## 16. Common Pitfalls When Registering a DataFetcher

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Field does not run the custom fetcher | Wrong GraphQL type or field name | Cross-check names in SDL and wiring |
| Application fails during schema creation | Registering a non-existent field or invalid schema | Check the schema and runtime wiring |
| Resolver runs but receives null arguments | Wrong argument name or schema allows null | Check `getArgument` and SDL |
| Custom resolver is never called | Competing wiring for the same field or duplicate controller mapping | Keep only one resolver per field coordinate |
| Request data leaks across users | Storing request state in a singleton `DataFetcher` | Use only local variables or execution-scoped context |
| Relationship field issues many queries | Each resolver calls the repository individually | Use `DataLoader` or `@BatchMapping` |
| Reactive field gets blocked | Using blocking APIs on an event loop | Choose reactive APIs or a suitable executor |
| GraphQL returns null after an error | Exception handler handled a field error | Check the error list and schema nullability |
| Client sees internal details | Returning raw exception messages | Map exceptions to safe messages |

## 17. Production Readiness Checklist

- Does the field exist in the schema, and do the wired type and field names match?
- Is a custom `DataFetcher` actually needed, or are `@QueryMapping`/`@SchemaMapping` sufficient?
- Does each GraphQL field coordinate have only a single registration mechanism?
- Does the `DataFetcher` receive dependencies via constructor and hold no request state?
- Are arguments checked for null, defaults, and input limits?
- Is authorization based on a trusted principal/context?
- Have relationship fields been evaluated for N+1 and `DataLoader`?
- Are exceptions mapped centrally without exposing internal details?
- Does the return type match the scalar/object/list type and nullability in the schema?
- Does async/reactive work use an appropriate executor or reactive pipeline?
- Are there unit tests for logic and integration tests for runtime wiring?
- Does logging avoid recording tokens, raw variables, or sensitive data?

A custom `DataFetcher` is a lower-level API for attaching data-retrieval logic directly to a GraphQL Java field. In Spring for GraphQL, use `RuntimeWiringConfigurer` to register resolvers and leverage Spring dependency injection; use controller annotations for standard fields. When implementing one, pay attention to request scoping, nullability, exception handling, authorization, `DataLoader`, and integration testing to ensure the resolver works properly across the entire GraphQL runtime.

## References

- [Spring Boot — GraphQL RuntimeWiring](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Data Integration](https://docs.spring.io/spring-graphql/reference/data.html)
- [GraphQL Java — Data Fetching](https://graphql-java.com/documentation/data-fetching/)
- [GraphQL Java — DataFetcher API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/schema/DataFetcher.html)
- [GraphQL Java — DataFetchingEnvironment API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/schema/DataFetchingEnvironment.html)
- [GraphQL Java — DataFetcherResult API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/execution/DataFetcherResult.html)
