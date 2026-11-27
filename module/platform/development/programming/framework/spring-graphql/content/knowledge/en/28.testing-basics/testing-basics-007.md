# Execute Mutation in Spring for GraphQL Testing

A Mutation is an operation used to modify data in GraphQL, such as creating an order, updating a profile, or cancelling a transaction. When testing a mutation, you need to verify two parts: that GraphQL receives the right document and variables, and that the resolver invokes the right business logic and returns a response matching the schema. Spring for GraphQL provides `GraphQlTester` to execute mutations and verify results without manually crafting HTTP requests in each test.

`GraphQlTester` uses the same workflow across multiple testing approaches: directly against the GraphQL execution service, via `WebGraphQlHandler`, or via HTTP/WebSocket/RSocket clients. For controller slice tests, `@GraphQlTest` auto-configures `GraphQlTester`; for end-to-end HTTP tests, you can use `HttpGraphQlTester`.

## 1. How Do Mutations Work in GraphQL?

GraphQL has three main operation types:

| Operation | Purpose | Response |
|---|---|---|
| Query | Reading data | A single GraphQL response. |
| Mutation | Modifying data | A single GraphQL response after processing the operation. |
| Subscription | Receiving events over time | A stream of multiple responses. |

Mutations typically accept an input object and return a payload describing the outcome. Example:

```graphql
input CreateBookInput {
    title: String!
    authorId: ID!
}

type Mutation {
    createBook(input: CreateBookInput!): CreateBookPayload!
}

type CreateBookPayload {
    book: Book
    userErrors: [UserError!]!
}

type Book {
    id: ID!
    title: String!
}

type UserError {
    code: String!
    message: String!
    field: [String!]
}
```

Clients can select the needed fields from the payload:

```graphql
mutation CreateBook($input: CreateBookInput!) {
    createBook(input: $input) {
        book {
            id
            title
        }
        userErrors {
            code
            message
            field
        }
    }
}
```

A Mutation is still a GraphQL request-response operation. In tests, call `execute()` to run the mutation and obtain a `GraphQlTester.Response`.

## 2. Testing Dependencies

Add the `spring-graphql-test` module to test scope:

```groovy
dependencies {
    testImplementation 'org.springframework.graphql:spring-graphql-test'
}
```

If the project uses Spring Boot, the dependency version is managed by Spring Boot dependency management. For controller slice tests, include the project's corresponding test starter, such as `spring-boot-starter-test`.

`spring-graphql-test` provides `GraphQlTester` and variants such as `ExecutionGraphQlServiceTester`, `WebGraphQlTester`, `HttpGraphQlTester`, `WebSocketGraphQlTester`, and `RSocketGraphQlTester`.

## 3. Preparing Controller and Service for the Mutation

Suppose the application has the following Java records:

```java
public record CreateBookInput(String title, String authorId) {}

public record Book(String id, String title) {}

public record UserError(
    String code,
    String message,
    List<String> field
) {}

public record CreateBookPayload(
    Book book,
    List<UserError> userErrors
) {}
```

Service responsible for business logic:

```java
public interface BookService {
    CreateBookPayload create(CreateBookInput input);
}
```

Controller mapping the mutation field:

```java
@Controller
class BookMutationController {

    private final BookService bookService;

    BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    CreateBookPayload createBook(@Argument("input") CreateBookInput input) {
        return bookService.create(input);
    }
}
```

`@MutationMapping` uses the method name `createBook` as the mutation field name by default. `@Argument("input")` binds the input object in the GraphQL document to `CreateBookInput`.

## 4. Using `@GraphQlTest` to Test Mutations

`@GraphQlTest` creates a test slice focused on Spring for GraphQL. It configures the schema, controllers, and `GraphQlTester` without starting an HTTP server. Collaborators such as services are typically replaced with mocks.

In Spring Boot 3.x, the annotation is in package `org.springframework.boot.test.autoconfigure.graphql.GraphQlTest`; in Spring Boot 4.x, the package is under `org.springframework.boot.graphql.test.autoconfigure`. Use the package matching your project's major version.

Example test:

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@GraphQlTest(BookMutationController.class)
class BookMutationTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @Test
    void createsBook() {
        CreateBookInput input = new CreateBookInput(
            "Spring GraphQL",
            "author-42"
        );

        given(bookService.create(any(CreateBookInput.class)))
            .willReturn(new CreateBookPayload(
                new Book("book-101", "Spring GraphQL"),
                List.of()
            ));

        graphQlTester.document("""
                mutation CreateBook($input: CreateBookInput!) {
                    createBook(input: $input) {
                        book {
                            id
                            title
                        }
                        userErrors {
                            code
                            message
                        }
                    }
                }
                """)
            .variable("input", Map.of(
                "title", "Spring GraphQL",
                "authorId", "author-42"
            ))
            .execute()
            .path("createBook.book.id")
            .entity(String.class)
            .isEqualTo("book-101");

        then(bookService).should().create(input);
    }
}
```

This example uses `@MockitoBean` from Spring Framework 6.2 and later. For older Spring Boot projects, you can use `@MockBean` according to the version in use. Commonly needed static imports:

```java
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;
import static org.mockito.Mockito.verifyNoInteractions;
```

`GraphQlTester` is auto-configured by `@GraphQlTest`. The test sends the mutation through GraphQL execution, reads `createBook.book.id` in `data`, and verifies that the service was called with the expected input.

## 5. Passing Input Using GraphQL Variables

Pass mutation data via variables instead of concatenating input strings into the GraphQL document. This keeps the document readable, avoids escaping errors, and simulates how real clients send operations.

The examples in the following sections reuse this document and variables:

```java
private static final String createBookMutation = """
    mutation CreateBook($input: CreateBookInput!) {
        createBook(input: $input) {
            book { id title }
            userErrors { code message field }
        }
    }
    """;

private static final Map<String, Object> inputVariables = Map.of(
    "title", "Spring GraphQL",
    "authorId", "author-42"
);
```

Example:

```java
graphQlTester.document("""
        mutation CreateBook($input: CreateBookInput!) {
            createBook(input: $input) {
                book { id title }
            }
        }
        """)
    .variable("input", Map.of(
        "title", "GraphQL for Java",
        "authorId", "author-7"
    ))
    .execute();
```

`variable(name, value)` binds a single variable to the request. If you need multiple variables, you can use `.variables(Map<String, Object>)`:

```java
Map<String, Object> variables = Map.of(
    "input", Map.of(
        "title", "GraphQL for Java",
        "authorId", "author-7"
    )
);

graphQlTester.document(mutationDocument)
    .variables(variables)
    .execute();
```

The variable name must match the `$input` declaration in the document. The map structure must match the input type in SDL; for example, `authorId` is `ID!`, so it can be sent as an ID string.

## 6. Storing Mutation Documents in `.graphql` Files

When a mutation is long or reused across multiple tests, you can store the document in `src/test/resources/graphql-test/`:

```text
src
└── test
    └── resources
        └── graphql-test
            └── createBook.graphql
```

Contents of `createBook.graphql`:

```graphql
mutation CreateBook($input: CreateBookInput!) {
    createBook(input: $input) {
        book {
            id
            title
        }
        userErrors {
            code
            message
            field
        }
    }
}
```

Test referencing it by `documentName`:

```java
graphQlTester.documentName("createBook")
    .variable("input", Map.of(
        "title", "Spring GraphQL",
        "authorId", "author-42"
    ))
    .execute()
    .path("createBook.book.title")
    .entity(String.class)
    .isEqualTo("Spring GraphQL");
```

`documentName("createBook")` looks for `createBook.graphql` in the default `graphql-test/` document source on the classpath. You can configure a custom `DocumentSource` if the project stores GraphQL documents elsewhere.

## 7. Verifying Multiple Fields in a Mutation Response

`GraphQlTester.Response.path(...)` uses JsonPath relative to the `data` section of the GraphQL response. You can inspect multiple fields in the same response:

```java
GraphQlTester.Response response = graphQlTester
    .document(createBookMutation)
    .variable("input", inputVariables)
    .execute();

response.path("createBook.book.id")
    .entity(String.class)
    .isEqualTo("book-101");

response.path("createBook.book.title")
    .entity(String.class)
    .isEqualTo("Spring GraphQL");

response.path("createBook.userErrors")
    .entityList(UserError.class)
    .hasSize(0);
```

If the response path uses an alias, use the alias in the path. For example, with `saved: createBook(...)`, the path starts with `saved`, not `createBook`.

For scalar or object fields, use `entity(Class)`; for lists, use `entityList(Class)` and check size or contents. You can use `.path("...").value()` when you need the raw value for custom assertions.

## 8. Verifying Business Errors in the Payload

Business validation is often an expected outcome of a mutation—for example, a duplicate title or a current state that does not allow the action. An API may return `userErrors` in the payload instead of throwing an exception.

Test for an already existing title:

```java
@Test
void returnsUserErrorWhenTitleAlreadyExists() {
    given(bookService.create(any(CreateBookInput.class)))
        .willReturn(new CreateBookPayload(
            null,
            List.of(new UserError(
                "DUPLICATE_TITLE",
                "A book with this title already exists",
                List.of("input", "title")
            ))
        ));

    GraphQlTester.Response response = graphQlTester.document(createBookMutation)
        .variable("input", Map.of(
            "title", "Existing title",
            "authorId", "author-42"
        ))
        .execute();

    // User error is inside the data payload, not a top-level GraphQL error.
    response.path("createBook.book").valueIsNull();
    response.path("createBook.userErrors[0].code")
        .entity(String.class)
        .isEqualTo("DUPLICATE_TITLE");
}
```

Do not use `.errors().verify()` for business errors inside the payload because they are not errors in top-level `errors`. Clients should read `userErrors.code` according to the schema contract.

## 9. Verifying GraphQL Errors from a Mutation

Execution errors occur when a resolver/service throws an exception and that exception is mapped to a GraphQL error. In that case, the response may contain partial or `null` `data` alongside an `errors` list.

Example checking an error code/message:

```java
GraphQlTester.Response response = graphQlTester
    .document(createBookMutation)
    .variable("input", inputVariables)
    .execute();

response.errors()
    .expect(error -> error.getMessage().contains("Book service unavailable"))
    .verify();
```

`errors().expect(...)` requires at least one error matching the predicate; `verify()` asserts the expected errors. You can then continue checking `data` if GraphQL returned partial data.

If you want to inspect the entire error list, use `satisfy`:

```java
response.errors().satisfy(errors ->
    assertThat(errors).anyMatch(error ->
        "BOOK_SERVICE_UNAVAILABLE".equals(
            error.getExtensions().get("code")
        )
    )
);
```

When using `satisfy`, errors are considered handled so you can continue asserting data. Avoid broadly filtering out errors just to keep tests passing; assert the exact expected error type.

## 10. Testing Input Coercion and Validation

GraphQL checks input types before invoking resolvers. If a mutation declares:

```graphql
input CreateBookInput {
    title: String!
    authorId: ID!
}
```

then variables missing `title`, passing `null` for `authorId`, or passing a wrongly typed object are rejected before `BookMutationController.createBook` runs.

Example testing a missing Non-null field:

```java
@Test
void rejectsInputWithoutRequiredTitle() {
    GraphQlTester.Response response = graphQlTester
        .document(createBookMutation)
        .variable("input", Map.of("authorId", "author-42"))
        .execute();

    response.errors().satisfy(errors ->
        assertThat(errors).isNotEmpty()
    );

    verifyNoInteractions(bookService);
}
```

Coercion/validation errors happen before execution, so the service is never called. Exact message text may vary across GraphQL Java versions; when checking details, prefer asserting stable error locations or classifications rather than relying on exact wording.

GraphQL input coercion differs from business validation. For example, an empty title string still satisfies the `String!` type; if the domain disallows empty titles, the service or Bean Validation must enforce that rule.

## 11. Verifying Mutations Without Top-Level Errors Using `executeAndVerify`

If a test only needs to verify that a mutation executed successfully without checking response fields, you can use `executeAndVerify()`:

Suppose the schema has a mutation returning a scalar:

```graphql
type Mutation {
    archiveBook(id: ID!): Boolean!
}
```

```java
graphQlTester.document("""
        mutation {
            archiveBook(id: "book-101")
        }
        """)
    .executeAndVerify();
```

This method executes the request and verifies that the response contains no GraphQL errors. It is suitable for mutations where the test only needs to verify there are no errors, such as scalar-returning operations or tests focused on separately mocked/verified side effects.

If you need to verify the returned value, use `execute()` and inspect the path:

```java
graphQlTester.document("""
        mutation {
            archiveBook(id: "book-101")
        }
        """)
    .execute()
    .path("archiveBook")
    .entity(Boolean.class)
    .isEqualTo(true);
```

`executeAndVerify()` does not replace assertions on returned data. A mutation can have zero GraphQL errors yet still return `false`, `null`, or a business error in the payload.

## 12. Verifying the Service Was Called Correctly

Checking the response tells you what the client receives; checking mock interactions tells you the resolver passed the input to the service as expected.

Example verifying input:

```java
then(bookService).should().create(
    new CreateBookInput("Spring GraphQL", "author-42")
);
```

You can use `ArgumentCaptor` when you need to inspect part of the input or normalized values:

```java
ArgumentCaptor<CreateBookInput> captor =
    ArgumentCaptor.forClass(CreateBookInput.class);

then(bookService).should().create(captor.capture());

assertThat(captor.getValue().title()).isEqualTo("Spring GraphQL");
assertThat(captor.getValue().authorId()).isEqualTo("author-42");
```

Do not verify only that the service was called while ignoring the response. A resolver could call the service properly yet map fields incorrectly or return the wrong payload; verify the response contract as well.

## 13. Testing Mutations with Database Side Effects

`@GraphQlTest` typically mocks services, so it does not prove that data is actually persisted to a database. When you need to verify persistence, transactions, or constraints, write an integration test with the application context and a test database.

Example test structure:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureHttpGraphQlTester
class BookMutationIntegrationTests {

    @Autowired
    HttpGraphQlTester graphQlTester;

    @Autowired
    BookRepository bookRepository;

    @Test
    void createsBookInDatabase() {
        graphQlTester.document(createBookMutation)
            .variable("input", Map.of(
                "title", "Spring GraphQL",
                "authorId", "author-42"
            ))
            .execute()
            .path("createBook.book.title")
            .entity(String.class)
            .isEqualTo("Spring GraphQL");

        assertThat(bookRepository.findByTitle("Spring GraphQL"))
            .isPresent();
    }
}
```

This example assumes the application provides `GraphQlTester` and `BookRepository` beans, a test database is configured, and the mutation writes real data. For applications requiring HTTP tests, use `@SpringBootTest` with `@AutoConfigureHttpGraphQlTester` or create `HttpGraphQlTester` from `WebTestClient`.

The package names for `@AutoConfigureHttpGraphQlTester` and GraphQL test annotations depend on the Spring Boot major line; use the package matching your project's version.

If a test needs to check HTTP status, headers, CORS, or the security filter chain, `GraphQlTester`'s transport abstraction may not be enough; use `WebTestClient`/MockMvc to assert HTTP details and `HttpGraphQlTester` to assert the GraphQL response.

## 14. Verifying Authorization When Executing Mutations

Mutations typically modify data, so you should test both allowed and denied cases. For example, a user lacking the `book:write` permission must not be able to create a book.

For slice tests with Spring Security method security, import the required security configuration or use an integration test to ensure the right filter/method security setup. Assertions should verify:

- Users with a valid authority can create data.
- Users lacking the authority do not invoke the data-writing service.
- Users cannot modify resources belonging to another tenant or owner.
- Error responses do not leak sensitive information.

Do not assume `@GraphQlTest` automatically loads the entire `SecurityFilterChain`, services, or application configuration. The test slice only includes supported GraphQL components and explicitly imported beans.

## 15. Distinguishing `@GraphQlTest`, `WebGraphQlTester`, and `HttpGraphQlTester`

| Tool | Scope | Suitable When |
|---|---|---|
| `@GraphQlTest` + `GraphQlTester` | Controller slice, no HTTP server | Checking SDL, argument binding, resolvers, responses, and exception mapping. |
| `WebGraphQlTester` | Through `WebGraphQlHandler` and interceptor chain | Checking web request metadata, GraphQL context, and interceptors. |
| `HttpGraphQlTester` | Over HTTP with `WebTestClient` | Checking HTTP endpoint, headers, and GraphQL responses. |
| `@SpringBootTest` | Full application context | Checking mutations with real services, repositories, transactions, and configuration. |

Start with slice tests for fast resolver verification. Use integration tests for behaviors that cannot be verified with mocks, such as database constraints, transaction rollbacks, HTTP security, and real serialization.

## 16. Notes When Testing Mutations

1. Use GraphQL variables instead of concatenating input strings directly into the document.
2. Select the right fields in the payload to verify the response contract.
3. Verify both service invocations and returned data.
4. Distinguish GraphQL input coercion, business validation, and execution errors.
5. For business errors in the payload, assert `userErrors`; do not look for them in top-level `errors`.
6. For execution errors, use `response.errors()` and check the necessary error codes/paths.
7. Do not use mock tests to conclude that the database persisted data correctly.
8. Do not automatically retry mutations in tests or clients without an idempotency strategy; retrying after a timeout can cause duplicate side effects.
9. Clean up test data or use an isolated database so tests do not depend on execution order.
10. Use document names for long and reused mutations to reduce duplication.

## 17. Common Errors

**Using `executeSubscription()` for mutations.** Mutations are request-response; use `execute()` or `executeAndVerify()`.

**Calling only `executeAndVerify()` and assuming the mutation returned the right data.** This method verifies there are no GraphQL errors; to check the payload, use `execute()` and `path(...)`.

**Declaring variables with the wrong type.** Variable names and input structures must match SDL. Coercion errors happen before resolvers run.

**Passing input via string concatenation.** Error-prone escaping and unreadable documents. Use `.variable(...)` or `.variables(...)`.

**Using `@GraphQlTest` but forgetting to mock services.** The test slice does not automatically load `@Service` and `@Repository`; use `@MockitoBean` or `@Import` the needed beans.

**Confusing business errors with GraphQL errors.** `userErrors` is data in the payload; top-level `errors` is for GraphQL/execution errors per the API contract.

**Asserting only that the service was called.** The resolver could still return wrong fields or the wrong payload. Check the response as well.

**Using mocks to conclude transactions/persistence work.** Real database or Testcontainers integration tests are required for those behaviors.

**Ignoring side effects when re-running tests.** Mutations can create duplicate records. Use unique test data, cleanup, or an appropriate transaction strategy.

## Conclusion

To execute mutations in Spring for GraphQL tests, build a request with `GraphQlTester.document(...)`, pass inputs via `.variable(...)` or `.variables(...)`, and call `.execute()` to inspect the response. Use `@GraphQlTest` and mock services for fast resolver tests; assert payload fields and verify that inputs are passed accurately. Distinguish business errors inside the payload from top-level GraphQL errors, use `executeAndVerify()` when you only need to confirm zero errors, and add integration tests when you need to prove that mutations actually write to the database and honor transactions or security.

## References

- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring Boot — Testing Spring GraphQL Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [GraphQL Specification — Mutation](https://spec.graphql.org/October2021/#sec-Mutation)
