# Controller slice testing

## 1. What is a controller slice test?

In Spring for GraphQL, controllers receive GraphQL operations through annotations such as `@QueryMapping`, `@MutationMapping`, `@SubscriptionMapping`, and `@SchemaMapping`. A controller typically calls services to fetch data, enforce business rules, or persist changes.

When testing a controller, you do not always need to start the entire application, database, message broker, and HTTP server. A controller slice test loads only the configuration required to execute GraphQL operations and invoke the controller under test. External services or collaborators are replaced with mocks.

Spring Boot provides the `@GraphQlTest` annotation for this purpose. It configures the GraphQL infrastructure, schema, and `GraphQlTester`, and restricts component scanning to components relevant to GraphQL controllers. Tests can send documents and variables and assert data and errors without exposing an HTTP endpoint or starting a server.

This is the right approach for verifying:

- GraphQL fields are mapped properly to controller methods.
- Arguments and variables are bound to the expected types.
- Nested field mappings such as `@SchemaMapping` work properly.
- The controller invokes the expected service with the received data.
- GraphQL schema validation rejects invalid operations.
- Exceptions are translated into GraphQL errors as configured by the controller.

## 2. Distinguishing controller slice tests from other test types

Different test types cover different scopes. Choosing the right one keeps tests focused without starting more components than necessary.

| Test type | Components under test | Transport/server involved? | Typical tools |
| --- | --- | --- | --- |
| Controller unit test | Direct Java methods and logic | No | JUnit, Mockito |
| `@GraphQlTest` | GraphQL schema, controller, argument binding, field mapping, GraphQL errors | No | `GraphQlTester` |
| `ExecutionGraphQlServiceTester` | Server-side GraphQL execution service | No | `GraphQlTester` |
| `WebGraphQlTester` | `WebGraphQlHandler`, `WebGraphQlInterceptor`, and simulated request metadata | No real HTTP server required | `GraphQlTester` |
| `HttpGraphQlTester` | GraphQL HTTP transport and server handler | Mock web environment or live server | `WebTestClient` |
| `WebSocketGraphQlTester` | WebSocket protocol and Subscriptions | Active WebSocket connection | `WebSocketClient`, Reactor Test |
| `@SpringBootTest` | Full application context and cross-layer integration | Depends on web environment | `GraphQlTester` or transport-specific tester |

`@GraphQlTest` does not test HTTP routes, WebSocket handshakes, web server filter chains, or reverse proxy configuration. When you need to verify those components, add integration tests with `HttpGraphQlTester`, `WebSocketGraphQlTester`, or `@SpringBootTest`.

## 3. Which components does `@GraphQlTest` load?

`@GraphQlTest` disables full auto-configuration and loads only a focused set of beans suitable for GraphQL testing. In current Spring Boot releases, recognized components include:

- `@Controller` — controllers handling GraphQL fields.
- `@ControllerAdvice` — shared exception handlers.
- `RuntimeWiringConfigurer` — custom scalar, directive, or DataFetcher registration.
- `@JacksonComponent` and `@JsonComponent` (the latter is deprecated) — Jackson support.
- `Converter` and `GenericConverter` — argument or data conversion.
- `DataFetcherExceptionResolver` — handling exceptions from GraphQL data fetchers.
- `Instrumentation` — GraphQL Java instrumentation.
- `GraphQlSourceBuilderCustomizer` — customizing GraphQL source creation.

Regular business beans such as `@Service`, `@Repository`, and `@Component` are not automatically scanned. This is intentional in slice tests: the controller is tested while its collaborators are mocked or selectively imported.

If no controllers are specified in `@GraphQlTest`, Spring Boot may add all matching controllers to the context. For focused tests, explicitly declare the controller under test:

```java
@GraphQlTest(BookController.class)
class BookControllerTests {
    // ...
}
```

## 4. Dependencies and package differences between Spring Boot 3 and 4

To use `GraphQlTester`, add the Spring for GraphQL test module:

```kotlin
dependencies {
    testImplementation("org.springframework.graphql:spring-graphql-test")
}
```

With Spring Boot 4, `@GraphQlTest` resides in the `spring-boot-graphql-test` module. The project also needs Spring Boot test support, for example:

```kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.boot:spring-boot-graphql-test")
    testImplementation("org.springframework.graphql:spring-graphql-test")
}
```

Spring Boot manages dependency versions via its dependency management/BOM. You do not need to specify versions manually if the project already uses Spring Boot dependency management.

The annotation package changes between major versions:

| Version | `@GraphQlTest` Import |
| --- | --- |
| Spring Boot 4.x | `org.springframework.boot.graphql.test.autoconfigure.GraphQlTest` |
| Spring Boot 3.x | `org.springframework.boot.test.autoconfigure.graphql.GraphQlTest` |

In Spring Framework 6.2 and later, you can use `@MockitoBean` from `org.springframework.test.context.bean.override.mockito.MockitoBean` to register mocks in the `ApplicationContext`. With Spring Boot 3.3 and earlier, projects typically used `@MockBean`; `@MockBean` was deprecated in Spring Boot 3.4 and replaced by `@MockitoBean` in newer releases.

## 5. Preparing a sample schema and controller

The examples use a book management API. Place the schema in `src/main/resources/graphql/schema.graphqls`:

```graphql
type Query {
    bookById(id: ID!): Book
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

Domain models:

```java
public record Book(String id, String title, String authorId) {
}

public record Author(String id, String name) {
}
```

Services used by the controller:

```java
public interface BookQueryService {
    Book findById(String id);
}

public interface AuthorQueryService {
    Author findById(String id);
}
```

Controller mapping the root Query field and the nested `Book.author` field:

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookQueryService bookQueryService;
    private final AuthorQueryService authorQueryService;

    public BookController(
            BookQueryService bookQueryService,
            AuthorQueryService authorQueryService) {
        this.bookQueryService = bookQueryService;
        this.authorQueryService = authorQueryService;
    }

    @QueryMapping
    public Book bookById(@Argument String id) {
        return bookQueryService.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorQueryService.findById(book.authorId());
    }
}
```

In the slice test, the real `BookController` is instantiated. The two services are replaced with Mockito mocks so the test does not access a database or external services.

## 6. Writing your first controller slice test

With Spring Boot 4, import the annotation from the new package. `@GraphQlTest` auto-configures `GraphQlTester`, so you only need to inject the tester and declare mocks for collaborators:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.graphql.test.autoconfigure.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;

@GraphQlTest(BookController.class)
class BookControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookQueryService bookQueryService;

    @MockitoBean
    AuthorQueryService authorQueryService;

    @Test
    void returnsBookById() {
        given(bookQueryService.findById("book-1"))
            .willReturn(new Book("book-1", "GraphQL in Action", "author-1"));

        graphQlTester.document("""
                query BookById($id: ID!) {
                    bookById(id: $id) {
                        id
                        title
                    }
                }
                """)
            .variable("id", "book-1")
            .execute()
            .errors()
            .verify()
            .path("bookById.id")
            .entity(String.class)
            .isEqualTo("book-1");

        then(bookQueryService).should().findById("book-1");
    }
}
```

Test flow:

1. `@GraphQlTest(BookController.class)` loads the GraphQL infrastructure, schema, and selected controller.
2. `@MockitoBean` registers a mocked `BookQueryService` in the application context.
3. `given(...).willReturn(...)` stubs the service result.
4. `document(...)` supplies the GraphQL operation.
5. `variable(...)` passes the value for `$id`.
6. `execute()` runs the operation through the GraphQL execution pipeline.
7. `errors().verify()` confirms the response contains no GraphQL errors.
8. `path(...)` selects a field under the `data` section of the response for assertion.
9. `then(...).should()` confirms the controller called the expected service.

The path `bookById.id` is evaluated relative to `data`, without needing a `data.` prefix.

## 7. Testing nested fields with `@SchemaMapping`

GraphQL can invoke multiple resolvers within the same operation. Controller slice tests should verify that both root fields and nested field mappings work properly.

```java
@Test
void resolvesNestedAuthorField() {
    given(bookQueryService.findById("book-1"))
        .willReturn(new Book("book-1", "GraphQL in Action", "author-1"));
    given(authorQueryService.findById("author-1"))
        .willReturn(new Author("author-1", "Sam"));

    graphQlTester.document("""
            query BookDetails($id: ID!) {
                bookById(id: $id) {
                    id
                    title
                    author {
                        id
                        name
                    }
                }
            }
            """)
        .variable("id", "book-1")
        .execute()
        .errors()
        .verify()
        .path("bookById.author.name")
        .entity(String.class)
        .isEqualTo("Sam");

    then(bookQueryService).should().findById("book-1");
    then(authorQueryService).should().findById("author-1");
}
```

This test verifies:

- `@QueryMapping` maps `bookById` properly.
- The resulting `Book` becomes the source object for nested fields.
- `@SchemaMapping(typeName = "Book", field = "author")` is invoked.
- The source object's `authorId` value is passed to the service.
- The GraphQL response contains nested data matching the selection set.

If a test only checks `bookById.id`, a bug in the `author` resolver can go undetected. Select all nested fields that real clients actually query.

## 8. Testing argument binding and GraphQL variables

`@Argument` binds an SDL argument to a method parameter. A controller slice test can verify that the value is bound properly by passing variables instead of concatenating strings directly into the query.

```java
@Test
void bindsGraphQlVariableToArgument() {
    given(bookQueryService.findById("book-42"))
        .willReturn(new Book("book-42", "Spring GraphQL", "author-7"));

    graphQlTester.document("""
            query FindBook($bookId: ID!) {
                bookById(id: $bookId) {
                    id
                }
            }
            """)
        .variable("bookId", "book-42")
        .execute()
        .errors()
        .verify()
        .path("bookById.id")
        .entity(String.class)
        .isEqualTo("book-42");

    then(bookQueryService).should().findById("book-42");
}
```

Using variables mirrors how real clients call the API and avoids rebuilding the document string for each value. You can also test `@Arguments`, input objects, enums, custom scalars, and nullable types defined in your application's schema.

## 9. Testing GraphQL schema validation

A major advantage of controller slice tests is that the schema is loaded alongside the GraphQL infrastructure. Consequently, tests can verify that invalid operations are rejected before the controller calls any service.

For example, the `bookById` field requires the `id: ID!` argument. A query missing the argument:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verifyNoInteractions;

@Test
void rejectsMissingRequiredArgument() {
    graphQlTester.document("""
            query {
                bookById {
                    id
                }
            }
            """)
        .execute()
        .errors()
        .satisfy(errors -> assertThat(errors).isNotEmpty());

    verifyNoInteractions(bookQueryService);
}
```

The test avoids asserting exact validation message wording, since messages may vary across GraphQL Java versions. It confirms that errors are present and that the service is not invoked.

You can apply the same pattern to test:

- Fields that do not exist in the schema.
- Missing required arguments.
- Scalars receiving values of the wrong type.
- Enums receiving undeclared values.
- Operations with invalid selection sets.
- Operation names that do not exist in a multi-operation document.

This is pre-execution schema validation. It is distinct from business validation inside services, such as checking whether a book exists or whether the user has permission to read it.

## 10. Testing GraphQL errors from resolvers

When a resolver or service throws an exception, Spring for GraphQL can translate it into a `GraphQLError` via `@GraphQlExceptionHandler`, `@ControllerAdvice`, or a `DataFetcherExceptionResolver`.

When testing a response expected to contain errors, do not call `errors().verify()` because that method asserts there are no errors. Instead, use `errors().satisfy(...)` or `errors().expect(...)`:

The example below assumes the application has an exception handler mapping `BookNotFoundException` to an appropriate GraphQL error message; the next section shows a concrete handler.

```java
@Test
void exposesExpectedGraphQlError() {
    given(bookQueryService.findById("missing"))
        .willThrow(new BookNotFoundException("Book not found"));

    graphQlTester.document("""
            query {
                bookById(id: "missing") {
                    id
                }
            }
            """)
        .execute()
        .errors()
        .satisfy(errors -> assertThat(errors)
            .anySatisfy(error ->
                assertThat(error.getMessage()).contains("Book not found")
            )
        );
}
```

`errors().satisfy(...)` lets you inspect the error list and marks the errors as handled in the test. If you want to verify that a specific error exists, you can use `errors().expect(predicate).verify()`.

In production, avoid relying on stack traces or internal exception messages. Prefer asserting standardized error codes in `extensions`, error classifications, or field paths produced by your exception handler.

## 11. Testing `@ControllerAdvice` and exception handlers

Current Spring Boot versions include GraphQL-related `@ControllerAdvice` beans in the slice test. If the application has a shared exception handler, verify that it is applied and returns the expected error contract.

Example handler:

```java
import java.util.Map;

import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GraphQlErrorAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(
            BookNotFoundException exception,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
            .message("Book not found")
            .extensions(Map.of("code", "BOOK_NOT_FOUND"))
            .build();
    }
}
```

The business exception in this example can be a simple runtime exception:

```java
public class BookNotFoundException extends RuntimeException {

    public BookNotFoundException(String message) {
        super(message);
    }
}
```

The test should verify the error code:

```java
@Test
void mapsBookNotFoundToStableErrorCode() {
    given(bookQueryService.findById("missing"))
        .willThrow(new BookNotFoundException("internal detail"));

    graphQlTester.document("{ bookById(id: \"missing\") { id } }")
        .execute()
        .errors()
        .satisfy(errors -> assertThat(errors).anySatisfy(error ->
            assertThat(error.getExtensions())
                .containsEntry("code", "BOOK_NOT_FOUND")
        ));
}
```

If the handler is not loaded, check your Spring Boot version, the component filter of `@GraphQlTest`, and how the advice is registered. With older slice tests or custom configurations, you can use `@Import(GraphQlErrorAdvice.class)` to include the advice explicitly in the context.

## 12. Organizing GraphQL documents in separate files

Long queries should be placed in `.graphql` or `.gql` files to keep tests readable and reusable. Spring GraphQL supports loading documents from the `graphql-test/` classpath directory via `documentName(...)`.

Example file `src/test/resources/graphql-test/book-details.graphql`:

```graphql
query BookDetails($id: ID!) {
    bookById(id: $id) {
        id
        title
        author {
            id
            name
        }
    }
}
```

Test:

```java
@Test
void loadsNamedDocument() {
    given(bookQueryService.findById("book-1"))
        .willReturn(new Book("book-1", "GraphQL in Action", "author-1"));
    given(authorQueryService.findById("author-1"))
        .willReturn(new Author("author-1", "Sam"));

    graphQlTester.documentName("book-details")
        .variable("id", "book-1")
        .execute()
        .errors()
        .verify()
        .path("bookById.author.name")
        .entity(String.class)
        .isEqualTo("Sam");
}
```

`documentName("book-details")` references `book-details.graphql`; no extension is needed. You can put fragments in separate files and include them with `fragmentName(...)` when multiple operations share selection sets.

## 13. When you need to import additional components or configuration

`@GraphQlTest` only loads bean types covered by its component filter. If a controller depends on a converter, scalar, configuration, or helper outside that filter, import it explicitly instead of broadening the entire component scan.

Example:

```java
import org.springframework.context.annotation.Import;

@GraphQlTest(BookController.class)
@Import(BookGraphQlTestConfiguration.class)
class BookControllerTests {
    // ...
}
```

`BookGraphQlTestConfiguration` can declare a `RuntimeWiringConfigurer`, custom scalars, Jackson modules, or test-specific helper beans. Avoid importing large production configurations if doing so pulls in databases, message brokers, or unrelated integrations.

If a `@ConfigurationProperties` bean is needed in the slice, use `@EnableConfigurationProperties(...)` or import the appropriate configuration. Test properties can be set via the `properties` attribute on `@GraphQlTest`:

```java
@GraphQlTest(
    controllers = BookController.class,
    properties = "catalog.feature.enabled=true"
)
class BookControllerTests {
    // ...
}
```

## 14. Verifying that the controller invokes services properly

Asserting the response alone is not enough to confirm whether the controller passed the right arguments to the service. Mockito can verify invocations and invocation counts:

```java
import static org.mockito.Mockito.times;

then(bookQueryService).should().findById("book-1");
then(authorQueryService).should(times(1)).findById("author-1");
```

Or confirm that the service is never called when GraphQL validation fails:

```java
verifyNoInteractions(bookQueryService);
```

Prefer verifying behavior that matters to the controller contract: accurate arguments, collaborators invoked when expected, and not invoked when operations are invalid. Avoid verifying every internal call if it is not part of the contract you want to protect.

For controllers with multiple services, mock only the controller's direct collaborators. When you need to test business rules inside a service, write dedicated service unit tests or appropriate integration tests.

## 15. Common `GraphQlTester` operations

`GraphQlTester` exposes a consistent API across transport-based and server-side testers. Common operations include:

| API | Purpose |
| --- | --- |
| `document(String)` | Send a GraphQL document inline from a string |
| `documentName(String)` | Load a document from the `graphql-test/` classpath directory |
| `variable(name, value)` | Assign a value to a GraphQL variable |
| `fragmentName(name)` | Load a fragment from a document file |
| `execute()` | Execute the operation and obtain a response for inspection |
| `executeAndVerify()` | Execute and verify the response has no GraphQL errors |
| `executeSubscription()` | Execute a Subscription and obtain a stream of results |
| `path(path)` | Select a field using a JsonPath relative to `data` |
| `entity(Class)` | Decode a single value into a Java type |
| `entityList(Class)` | Decode a list into a Java type |
| `matchesJson(String)` | Compare data at the path against expected JSON |
| `errors().verify()` | Confirm no unhandled GraphQL errors remain |
| `errors().expect(...)` | Assert that an error matches a predicate |
| `errors().satisfy(...)` | Inspect the full error list with assertions |

If testing a Mutation with no response data to inspect, `executeAndVerify()` is a concise way to assert there are no errors. If the response includes data to check, use `execute()` and assert the necessary paths.

## 16. When to switch to `HttpGraphQlTester` or `@SpringBootTest`?

`@GraphQlTest` does not run an HTTP server. If a test must verify the `/graphql` endpoint, HTTP headers, authentication filters, or a `WebGraphQlInterceptor`, expand the test scope.

With Spring Boot, one option is:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.graphql.test.autoconfigure.tester.AutoConfigureHttpGraphQlTester;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.HttpGraphQlTester;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureHttpGraphQlTester
class BookGraphQlIntegrationTests {

    @Test
    void executesThroughHttp(@Autowired HttpGraphQlTester graphQlTester) {
        graphQlTester.document("{ bookById(id: \"book-1\") { id } }")
            .execute()
            .errors()
            .verify()
            .path("bookById.id")
            .entity(String.class)
            .isEqualTo("book-1");
    }
}
```

With `RANDOM_PORT`, Spring Boot starts a live server on a random port. `HttpGraphQlTester` sends requests over HTTP transport to that server. This works well for select integration tests, though it is slower than a controller slice and may require a real database or test fixtures.

If you only need to test a `WebGraphQlInterceptor` without an HTTP server, you can use `WebGraphQlTester` backed by `WebGraphQlHandler`. When testing WebSocket Subscriptions, use `WebSocketGraphQlTester` and manage the connection lifecycle in the test.

## 17. Common mistakes when writing controller slice tests

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Service bean not found during context startup | `@Service` is not scanned in the slice | Use `@MockitoBean` or `@Import` for required collaborators |
| Cannot inject `GraphQlTester` | Missing `spring-graphql-test` or wrong Boot test module | Check test dependencies and auto-configuration |
| `@GraphQlTest` not found | Wrong package import for the Boot version | Boot 4 uses `org.springframework.boot.graphql.test.autoconfigure`; Boot 3 uses the older package |
| Schema missing a field in tests | SDL is not in the configured schema location or schema is invalid | Check `src/main/resources/graphql` and GraphQL schema locations |
| Controller is not invoked | Controller not specified or method mapping does not match SDL | Check `@GraphQlTest(Controller.class)`, root type, and field name |
| Nested field returns null | Missing `@SchemaMapping` or source object lacks the matching property | Check field mapping and source data |
| Test passes even though response has errors | Used `execute()` without checking errors | Add `.errors().verify()` or use `.executeAndVerify()` |
| Test fails with unexpected error assertion | Called `errors().verify()` in a case expecting errors | Use `errors().expect(...)` or `errors().satisfy(...)` |
| Mockito records no invocations | Query did not select the field, schema validation failed, or argument stubbing mismatched | Check the document, variables, and mock setup |
| `@ControllerAdvice` is not applied | Advice is not scanned/imported in the slice for the Boot version in use | Check component filters or use `@Import` |
| Production config pulls database into test | Imported full configuration or broadened component scan | Import only needed config and mock collaborators |
| Expected HTTP test only runs GraphQL execution | `@GraphQlTest` does not set up transport/server | Use `HttpGraphQlTester` and `@SpringBootTest` when needed |

## 18. Checklist for controller slice tests

- [ ] Add `spring-graphql-test` to test dependencies.
- [ ] Use `@GraphQlTest` with the specific controllers under test.
- [ ] Use the `@GraphQlTest` package matching your Spring Boot version.
- [ ] Inject the auto-configured `GraphQlTester`.
- [ ] Replace dependent services/repositories with `@MockitoBean` or selective imports.
- [ ] Place the SDL schema in the location configured by Spring Boot.
- [ ] Send operations with `document(...)` or `documentName(...)`.
- [ ] Use GraphQL variables to verify argument binding.
- [ ] Test both root fields and nested fields if the controller defines `@SchemaMapping`.
- [ ] Use `errors().verify()` for responses expected to have no errors.
- [ ] Use `errors().expect(...)` or `errors().satisfy(...)` for responses expected to have errors.
- [ ] Verify the service is invoked properly or not invoked when validation fails.
- [ ] Explicitly import required advice, converters, scalars, or configuration.
- [ ] Switch to HTTP/WebSocket integration tests when transport verification is required.

## Conclusion

`@GraphQlTest` is Spring Boot's tool for testing GraphQL controllers within a bounded `ApplicationContext`. It loads the GraphQL infrastructure, schema, controllers, and relevant extension points while auto-configuring `GraphQlTester`. Regular services and repositories are not scanned, so replace them with `@MockitoBean` or import them individually when truly needed.

A controller slice test can verify SDL-to-`@QueryMapping`/`@SchemaMapping` mappings, argument binding, nested selection sets, schema validation, service interactions, and GraphQL errors without an HTTP server. Use `GraphQlTester` to assert data and errors, keep tests focused on the controller's GraphQL contract, and complement them with integration tests using `HttpGraphQlTester` or `WebSocketGraphQlTester` for transport-level behavior.

## References

- [Spring Boot 4.2 — Auto-configured Spring GraphQL Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.autoconfigured-spring-graphql-tests)
- [Spring Boot — `@GraphQlTest` API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/graphql/test/autoconfigure/GraphQlTest.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring Framework — Mockito Bean Overrides](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html)
- [Spring Getting Started — Building a GraphQL service](https://spring.io/guides/gs/graphql-server)
