# Execute Query

## Objectives

After this lesson, you will be able to:

- Explain the role of GraphQlTester when executing a GraphQL query in tests.
- Create requests from a GraphQL document, operation name, and variables.
- Call execute() and read GraphQL responses.
- Extract fields using JsonPath and map them to Java objects.
- Verify scalars, objects, lists, and JSON structures.
- Read and verify GraphQL errors, including when responses contain partial data.
- Load queries from classpath files and attach fragments.
- Choose the appropriate GraphQlTester for the testing scope.
- Distinguish testing execution from testing HTTP transport.
- Write tests for successful Queries, missing data, and resolver errors.

## 1. What Is Executing a Query in GraphQL Testing?

When building a GraphQL server, testing a service method in isolation is not enough to guarantee the API works properly. A query goes through many steps: the GraphQL document is parsed, validated against the schema, variables are coerced, fields are mapped to DataFetchers, resolvers invoke services, and results are serialized into a GraphQL response.

Spring for GraphQL provides GraphQlTester to execute GraphQL requests in tests and assert responses using the same workflow, independent of the transport used.

A typical test looks like:

~~~java
graphQlTester.document("""
        query {
            bookById(id: "b-01") {
                id
                title
            }
        }
        """)
        .execute()
        .path("bookById.id")
        .entity(String.class)
        .isEqualTo("b-01");
~~~

The flow above consists of:

1. document(...) supplies the GraphQL operation.
2. execute() runs the request through the configured GraphQlTester.
3. path(...) selects data in the response using JsonPath.
4. entity(...) decodes the value into a Java type.
5. isEqualTo(...) verifies that the actual value matches the expected value.

In this lesson, "execute query" mainly refers to running a GraphQL request in a test. Distinguish this from GraphQlTester's execute() method: execute() is the method that starts executing the declared request, while query is the operation type that the document asks the server to run.

## 2. GraphQlTester and Tester Types

GraphQlTester is the common abstraction for writing GraphQL tests. The same way of building documents, passing variables, executing, and asserting responses can be used across multiple transports.

Spring for GraphQL provides implementations suited to different testing scopes:

| Tester | Testing Scope | Is an HTTP Server Needed? |
|---|---|---|
| ExecutionGraphQlServiceTester | Executes via ExecutionGraphQlService | No |
| WebGraphQlTester | Executes via WebGraphQlHandler, including interceptor chain | No HTTP server needed |
| HttpGraphQlTester | Sends requests over HTTP to the server | Can use a live server or mock web transport |
| WebSocketGraphQlTester | Sends operations over WebSocket | Requires configured WebSocket transport |
| RSocketGraphQlTester | Sends operations over RSocket | Requires RSocket transport |

For typical Query tests, you can use the GraphQlTester auto-configured by Spring Boot in a test slice or ExecutionGraphQlServiceTester. If you need to verify HTTP endpoints, headers, authentication, and status codes, use HttpGraphQlTester combined with appropriate web testing support.

GraphQlTester helps verify the path from a GraphQL document to its response. It does not replace unit tests for services or repositories. Choose the test layer based on the behavior you want to verify.

## 3. Adding Testing Libraries

Spring for GraphQL provides a dedicated module containing GraphQlTester. With Maven:

~~~xml
<dependency>
    <groupId>org.springframework.graphql</groupId>
    <artifactId>spring-graphql-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

With Gradle:

~~~groovy
testImplementation("org.springframework.graphql:spring-graphql-test")
~~~

If testing over HTTP with WebTestClient and the application does not yet have WebFlux on the test classpath, you may need to add the WebFlux starter in test scope:

~~~groovy
testImplementation("org.springframework.boot:spring-boot-starter-webflux")
~~~

For Spring MVC applications, you can use MockMvcWebTestClient to create an HttpGraphQlTester without switching the web stack to WebFlux. Choose the right test client for your application's transport.

Use Spring Boot dependency management to select compatible versions across Spring Boot, Spring for GraphQL, and spring-graphql-test. Do not manually choose a test module version that differs from the dependency line used by the application.

## 4. Preparing Schema, Controller, and Model

Suppose an application has a Query to fetch a book by ID.

Schema in src/main/resources/graphql/schema.graphqls:

~~~graphql
type Query {
  bookById(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  publishedYear: Int
}
~~~

Model:

~~~java
public record Book(
        String id,
        String title,
        Integer publishedYear) {
}
~~~

Service:

~~~java
public interface BookService {
    Book findById(String id);
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
    public Book bookById(@Argument String id) {
        return bookService.findById(id);
    }
}
~~~

The bookById query field accepts an id argument and returns a Book or null if not found. Because the Book field is declared nullable in SDL, the server can return null without necessarily producing an execution error.

Tests need to verify multiple layers working together:

- The schema recognizes the Query and the bookById field.
- The id argument is bound properly.
- @QueryMapping is invoked.
- The service receives the right ID.
- Book is serialized with the fields selected by the client.

## 5. Writing Controller Tests with @GraphQlTest

Spring Boot provides @GraphQlTest to test GraphQL controllers without starting an HTTP server. This annotation configures the GraphQL infrastructure and loads only the group of beans relevant for GraphQL tests.

Example:

~~~java
@GraphQlTest(BookController.class)
class BookControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @Test
    void shouldReturnBookById() {
        when(bookService.findById("b-01"))
                .thenReturn(new Book(
                        "b-01",
                        "GraphQL in Practice",
                        2026));

        graphQlTester.document("""
                query BookById($id: ID!) {
                    bookById(id: $id) {
                        id
                        title
                        publishedYear
                    }
                }
                """)
                .operationName("BookById")
                .variable("id", "b-01")
                .execute()
                .path("bookById.id")
                .entity(String.class)
                .isEqualTo("b-01");
    }
}
~~~

In this example:

- @GraphQlTest(BookController.class) focuses only on the specified controller and related GraphQL infrastructure.
- GraphQlTester is auto-configured.
- @MockitoBean provides a mock BookService because regular services are not automatically loaded in the test slice.
- when(...).thenReturn(...) sets up test data.
- execute() runs the Query through the GraphQL engine.
- path(...) selects fields in the response for assertions.

In Spring Boot 4, the package for @GraphQlTest is org.springframework.boot.graphql.test.autoconfigure. In Spring Boot 3, the package is org.springframework.boot.test.autoconfigure.graphql. Newer Spring Framework versions support @MockitoBean; in older Boot projects, you may need to use @MockBean depending on the version in use.

In Boot 4, the @GraphQlTest annotation is provided by the spring-boot-graphql-test module. @MockitoBean lives in the org.springframework.test.context.bean.override.mockito package. Boot 3.4 and later can also use @MockitoBean; older Boot versions typically use @MockBean from Spring Boot.

@GraphQlTest is not a full application test. Services, repositories, or configurations outside the scanned bean set must be provided using mocks or @Import.

## 6. Creating Requests with document()

document(String) accepts a GraphQL document as a string. A document can contain one or more operations, fragments, and variable definitions.

Simple query example:

~~~java
graphQlTester.document("{ bookById(id: \"b-01\") { id title } }")
        .execute()
        .path("bookById.title")
        .entity(String.class)
        .isEqualTo("GraphQL in Practice");
~~~

For longer queries, Java text blocks keep the GraphQL structure readable:

~~~java
String query = """
        query BookById($id: ID!) {
            bookById(id: $id) {
                id
                title
            }
        }
        """;

graphQlTester.document(query)
        .execute()
        .path("bookById")
        .matchesJson("""
                {
                    "id": "b-01",
                    "title": "GraphQL in Practice"
                }
                """);
~~~

document() only builds the request specification. The request is only executed when calling execute() or a corresponding execution method such as executeAndVerify() or executeSubscription().

Do not concatenate strings by embedding inputs directly into the GraphQL document. Use variables to keep queries stable and avoid escaping errors.

## 7. Passing Variables and operationName

Queries often declare variables to separate operation structure from input data.

Example:

~~~graphql
query SearchBooks($keyword: String!, $first: Int!) {
  searchBooks(keyword: $keyword, first: $first) {
    id
    title
  }
}
~~~

In a test:

~~~java
graphQlTester.document("""
        query SearchBooks($keyword: String!, $first: Int!) {
            searchBooks(keyword: $keyword, first: $first) {
                id
                title
            }
        }
        """)
        .operationName("SearchBooks")
        .variable("keyword", "Spring")
        .variable("first", 10)
        .execute()
        .path("searchBooks")
        .entityList(Book.class)
        .hasSize(10);
~~~

You can pass multiple variables via a Map:

~~~java
Map<String, Object> variables = Map.of(
        "keyword", "Spring",
        "first", 10
);

graphQlTester.document(query)
        .operationName("SearchBooks")
        .variables(variables)
        .execute();
~~~

operationName is required when a document contains multiple operations so the server knows which operation is requested. When a document has only one operation, operationName can be omitted, though naming it still makes tests and logs easier to read.

The GraphQL server still validates variable types against SDL. Tests should include valid variables, wrongly typed variables, missing required variables, and nullable variables receiving null when those are behaviors to verify.

## 8. Reading Responses with path()

After execute(), GraphQlTester returns a Response spec. Use path(...) to select a portion of data to assert.

Example:

~~~java
graphQlTester.document(query)
        .variable("id", "b-01")
        .execute()
        .path("bookById.id")
        .entity(String.class)
        .isEqualTo("b-01");
~~~

JsonPath paths are evaluated relative to the data section of the GraphQL response by default. Therefore, there is no need to add a data prefix.

Given this response:

~~~json
{
  "data": {
    "bookById": {
      "id": "b-01",
      "title": "GraphQL in Practice"
    }
  }
}
~~~

The right path is bookById.id or bookById.title, not data.bookById.id.

You can assert multiple fields on the same response by calling path multiple times:

~~~java
GraphQlTester.Response response =
        graphQlTester.document(query)
                .variable("id", "b-01")
                .execute();

response.path("bookById.id")
        .entity(String.class)
        .isEqualTo("b-01");

response.path("bookById.title")
        .entity(String.class)
        .isEqualTo("GraphQL in Practice");
~~~

This avoids executing the same query multiple times just to assert different fields.

## 9. Verifying Scalars, Objects, and Lists

### Scalar

Use entity(Class) when the path points to a scalar value:

~~~java
graphQlTester.document("{ greeting }")
        .execute()
        .path("greeting")
        .entity(String.class)
        .isEqualTo("Hello, Spring!");
~~~

### Object

Use entity(Class) to decode an object into a DTO or record:

~~~java
graphQlTester.document(query)
        .variable("id", "b-01")
        .execute()
        .path("bookById")
        .entity(Book.class)
        .satisfies(book -> {
            assertThat(book.id()).isEqualTo("b-01");
            assertThat(book.title())
                    .isEqualTo("GraphQL in Practice");
        });
~~~

Only fields requested by the query appear in the response. The DTO used for decoding must be compatible with the selected field structure.

### List

Use entityList(Class) when the path returns an array:

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
        .entityList(Book.class)
        .hasSizeGreaterThan(0);
~~~

You can select fields inside each element using a JsonPath wildcard:

~~~java
graphQlTester.document("""
        query {
            books {
                title
            }
        }
        """)
        .execute()
        .path("books[*].title")
        .entityList(String.class)
        .contains("GraphQL in Practice");
~~~

Use wildcards when you want to check a property across all elements without depending on order. If ordering is part of the API contract, verify ordering explicitly.

## 10. Verifying JSON with matchesJson()

When you want to verify the structure of an entire object or list, matchesJson() helps compare against expected JSON.

Example:

~~~java
graphQlTester.document("""
        query {
            bookById(id: "b-01") {
                id
                title
            }
        }
        """)
        .execute()
        .path("bookById")
        .matchesJson("""
                {
                    "id": "b-01",
                    "title": "GraphQL in Practice"
                }
                """);
~~~

matchesJson() is appropriate when a test needs to verify multiple fields at once. For tests concerned with a single value, path(...).entity(...) is usually shorter and less coupled to unrelated structure.

matchesJson() requires the JSONassert library on the test classpath. If the project does not use this library, use entity(), entityList(), or path-by-path assertions instead.

Avoid comparing the entire response if a test only cares about a small subset. That makes tests fragile when the schema adds new fields without changing the behavior under test.

## 11. Checking Nested Paths

Responses can nest multiple objects. You can call path() with a callback to assert multiple fields relative to a parent object.

In this extended example, the schema adds an Author relationship:

~~~graphql
extend type Book {
  author: Author
}

type Author {
  id: ID!
  name: String!
}
~~~

The nested path, fragment, and partial data examples below assume the test fixture can provide an Author for Book, either via an existing property or a Book.author resolver.

Example query:

~~~graphql
query {
  bookById(id: "b-01") {
    id
    title
    author {
      id
      name
    }
  }
}
~~~

Test:

~~~java
graphQlTester.document("""
        query {
          bookById(id: "b-01") {
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
        .path("bookById", book -> book
                .path("id")
                .entity(String.class)
                .isEqualTo("b-01")
                .path("author.name")
                .entity(String.class)
                .isEqualTo("Nguyen An"));
~~~

Inside the callback, sub-paths are evaluated relative to the selected object. This is useful when a response has a deep structure and a test needs to assert multiple fields in the same branch.

You can combine nested paths with entity() to decode a sub-object into its own DTO.

## 12. Loading Queries from Files with documentName()

For long or reused queries, store GraphQL documents as files in test resources.

Example path:

~~~text
src/test/resources/graphql-test/bookById.graphql
~~~

Contents:

~~~graphql
query BookById($id: ID!) {
  bookById(id: $id) {
    id
    title
    publishedYear
  }
}
~~~

Test referencing the document by filename:

~~~java
graphQlTester.documentName("bookById")
        .variable("id", "b-01")
        .execute()
        .path("bookById.id")
        .entity(String.class)
        .isEqualTo("b-01");
~~~

By default, GraphQlTester's DocumentSource searches for .graphql or .gql files in the graphql-test/ classpath directory. You do not need to include the file extension when calling documentName().

Putting queries in files helps:

- Keep test methods focused on variables and assertions.
- Allow GraphQL documents to be reviewed independently.
- Enable IDE syntax highlighting and completion.
- Reuse operations across multiple tests.
- Prevent long queries from making Java tests hard to read.

Do not confuse GraphQlTester's graphql-test/ directory with graphql-documents/, which is commonly used for GraphQlClient in application code.

## 13. Reusing Fragments in Tests

GraphQL fragments allow sharing field selections across multiple operations.

Example fragment file:

~~~text
src/test/resources/graphql-test/authorFields.graphql
~~~

Contents:

~~~graphql
fragment authorFields on Author {
  id
  name
}
~~~

Query:

~~~graphql
query BookById($id: ID!) {
  bookById(id: $id) {
    author {
      ...authorFields
    }
  }
}
~~~

Save the query above in src/test/resources/graphql-test/bookWithAuthor.graphql so documentName("bookWithAuthor") can load the right file.

Test attaching the fragment from file:

~~~java
graphQlTester.documentName("bookWithAuthor")
        .fragmentName("authorFields")
        .variable("id", "b-01")
        .execute()
        .path("bookById.author.name")
        .entity(String.class)
        .isEqualTo("Nguyen An");
~~~

GraphQlTester supports fragment(...) to add a fragment as a string and fragmentName(...) to load a fragment via DocumentSource.

Fragments do not change the semantics of the selected fields. The GraphQL server still validates the fragment's type condition and the fields inside the fragment against the schema.

## 14. Execute and Handling GraphQL Errors

A GraphQL response can contain both data and errors at the same time. Therefore, tests need to clarify which errors are unexpected and which errors represent the behavior under test.

When calling verify(), any unfiltered errors in the response will cause the assertion to fail.

Example verifying that a field produces no errors:

~~~java
graphQlTester.document("""
        query {
          bookById(id: "b-01") {
            id
            title
          }
        }
        """)
        .execute()
        .errors()
        .verify();
~~~

If you want to verify that a specific error exists, use expect(...):

The example below assumes the resolver or service throws BookNotFoundException when the ID does not exist and the application maps that exception to a GraphQL error with a matching message.

~~~java
graphQlTester.document("""
        query {
            bookById(id: "missing") {
                id
                title
            }
        }
        """)
        .execute()
        .errors()
        .expect(error ->
                error.getMessage().contains("Book was not found"))
        .verify();
~~~

expect(...) fails the test if no matching error is found.

If an error is expected and you want to continue checking data, use filter(...):

~~~java
graphQlTester.document(query)
        .variable("id", "b-01")
        .execute()
        .errors()
        .filter(error ->
                error.getMessage().contains("Title unavailable"))
        .verify()
        .path("bookById.id")
        .entity(String.class)
        .isEqualTo("b-01");
~~~

Filter only errors that the test genuinely expects. Do not filter out all errors just to make a test pass, as doing so can hide resolver or schema bugs.

Use satisfy(...) when you need to check the entire error list with an assertion library:

~~~java
graphQlTester.document(query)
        .variable("id", "b-01")
        .execute()
        .errors()
        .satisfy(errors ->
                assertThat(errors)
                        .anyMatch(error ->
                                error.getMessage()
                                        .contains("Title unavailable")));
~~~

satisfy(...) lets you assert errors as a group and marks them as handled so the test can continue asserting response data if needed.

## 15. How Do execute() and executeAndVerify() Differ?

These two methods serve two purposes:

| Method | Result | When to Use |
|---|---|---|
| execute() | Returns GraphQlTester.Response to read data and errors | Queries needing field or response assertions |
| executeAndVerify() | Executes and verifies the response has no errors | Only needing to verify an operation has no GraphQL errors |

Example using execute():

~~~java
graphQlTester.document("""
        query {
            bookById(id: "b-01") {
                title
            }
        }
        """)
        .execute()
        .path("bookById.title")
        .entity(String.class)
        .isEqualTo("GraphQL in Practice");
~~~

Example using executeAndVerify():

~~~java
graphQlTester.document("""
        mutation {
            clearTestCache
        }
        """)
        .executeAndVerify();
~~~

executeAndVerify() does not replace assertions on return values. If you need to verify that a mutation returns true, a record count, or a new object, use execute() and inspect the corresponding path.

With HTTP-based testers, execute() and executeAndVerify() may report an assertion failure if the HTTP status is not 200 per GraphQlTester's contract. If you need to check 4xx/5xx status codes or HTTP-level content negotiation, use WebTestClient to verify the transport response separately.

## 16. Distinguishing Request Errors and Field Execution Errors

GraphQL can reject an operation before resolvers run or produce errors while resolving fields.

| Error Type | Stage | Example |
|---|---|---|
| Parse error | Parsing document | Missing brace or invalid syntax |
| Validation error | Schema validation | Querying a nonexistent field |
| Variable coercion error | Coercing variables | Passing a string for an Int variable |
| Field execution error | Resolver execution | Service throws an exception |
| Serialization error | Building response | Custom scalar fails to serialize |

Request errors usually prevent GraphQL from producing normal execution data. Field execution errors can produce partial responses containing both data and errors.

Example field execution error:

~~~json
{
  "data": {
    "bookById": {
      "id": "b-01",
      "title": null
    }
  },
  "errors": [
    {
      "message": "Unable to load title",
      "path": ["bookById", "title"]
    }
  ]
}
~~~

When testing errors, check the message or error code, path, and impact on data according to nullability. Checking only that the errors list is non-empty is rarely enough to verify that the API honors its contract.

## 17. Verifying Partial Data Alongside Errors

One field may fail while other fields still return data. This is a key GraphQL behavior.

Example query:

~~~graphql
query {
  bookById(id: "b-01") {
    id
    title
    author {
      name
    }
  }
}
~~~

Suppose the author resolver errors, yet Book can still return id and title. A test can check both the error and data:

~~~java
graphQlTester.document("""
        query {
          bookById(id: "b-01") {
            id
            title
            author {
              name
            }
          }
        }
        """)
        .execute()
        .errors()
        .satisfy(errors ->
                assertThat(errors)
                        .anyMatch(error ->
                                error.getPath().contains("author")))
        .path("bookById.id")
        .entity(String.class)
        .isEqualTo("b-01");
~~~

Design assertions according to SDL nullability. If the author field is nullable, an error in author may simply make author null. If a non-null field yields null, GraphQL can bubble null up to the nearest nullable parent.

Do not assume every field error turns the entire data section into null.

## 18. Testing Queries When Data Is Not Found

For nullable fields, a service can return null when an object is not found. Tests should confirm the response has null and no error if that is the API contract.

Example:

~~~java
@Test
void shouldReturnNullWhenBookDoesNotExist() {
    when(bookService.findById("missing"))
            .thenReturn(null);

    graphQlTester.document("""
            query {
                bookById(id: "missing") {
                    id
                    title
                }
            }
            """)
            .execute()
            .path("bookById")
            .valueIsNull();

    verify(bookService).findById("missing");
}
~~~

If the field is declared non-null in SDL, returning null behaves differently: GraphQL produces an execution error and applies null propagation. Tests must verify the actual schema contract rather than only checking that the Java service returns null.

When testing missing data, distinguish clearly between:

- Missing data is a valid business outcome.
- The resolver throws an error because the data was not found.
- The request is invalid, so the resolver is never called.

These three cases can produce different responses and need separate tests if the API supports them.

## 19. Using GraphQlTester for Full Integration Tests

@GraphQlTest is well suited for controller slice tests. When you want to verify the entire application, use @SpringBootTest and HttpGraphQlTester.

Example:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureHttpGraphQlTester
class GraphQlHttpIntegrationTests {

    @Autowired
    HttpGraphQlTester graphQlTester;

    @Test
    void shouldExecuteBookQueryThroughHttp() {
        graphQlTester.document("""
                query {
                    bookById(id: "b-01") {
                        id
                        title
                    }
                }
                """)
                .execute()
                .path("bookById.id")
                .entity(String.class)
                .isEqualTo("b-01");
    }
}
~~~

With this test:

- The Spring Boot application is started.
- The GraphQL HTTP endpoint is called over real transport.
- Web components, security filters, and GraphQL infrastructure can all participate.
- The tester verifies the response from the running server.

In Spring Boot 4, AutoConfigureHttpGraphQlTester belongs to the org.springframework.boot.graphql.test.autoconfigure.tester package. In Spring Boot 3, the package is org.springframework.boot.test.autoconfigure.graphql.tester.

If you only need to test the HTTP handler in a mock web environment, you can configure the tester with the appropriate web test client. You do not need to start a real server for every test; choose full integration tests when transport or web configuration is part of the behavior under verification.

## 20. Testing Timeouts and Asynchronous Responses

GraphQlTester has a response timeout to prevent tests from waiting indefinitely when an operation does not complete. The builder lets you customize a timeout suitable for the test:

~~~java
GraphQlTester tester = GraphQlTester.builder(transport)
        .responseTimeout(Duration.ofSeconds(10))
        .build();
~~~

The example above illustrates configuration for a tester created from GraphQlTransport. For testers auto-configured by Spring Boot, you can use mutate() to create a new tester with modified settings if the transport builder supports it.

Do not increase timeouts to hide slow resolvers. Distinguish between slow tests caused by the environment and operations that genuinely hang or make overly slow downstream calls.

With reactive controllers, GraphQlTester waits for the GraphQL response to complete. There is no need to call subscribe() manually in tests to trigger the resolver. Let the tester execute the request and manage collecting results.

## 21. Subscription Testing Differs from Query Testing

Queries return a single response per operation. Subscriptions produce a stream of responses per event, so use executeSubscription() instead of execute().

Example:

~~~java
Flux<String> greetings = graphQlTester.document(
                "subscription { greetings }")
        .executeSubscription()
        .toFlux("greetings", String.class);

StepVerifier.create(greetings)
        .expectNext("Hi")
        .expectNext("Bonjour")
        .expectNext("Hola")
        .verifyComplete();
~~~

executeSubscription() returns a subscription spec to convert the response stream into a Flux or inspect individual events. GraphQlTester supports subscriptions with WebSocketGraphQlTester or certain server-side extensions such as ExecutionGraphQlServiceTester and WebGraphQlTester.

Do not use execute() for a subscription and expect multiple responses. Queries and Subscriptions have different lifecycles.

## 22. Common Errors When Executing Queries

| Symptom | Possible Cause | Resolution |
|---|---|---|
| GraphQlTester is not injected | Missing spring-graphql-test or test auto-configuration | Check dependencies and annotations |
| Query returns unexpected null | Wrong field path, argument, or service fixture | Check schema, document, and mock setup |
| Path not found | Incorrect path or field is not in data | Inspect response JSON and use a path relative to data |
| Test fails due to errors | Resolver produced an unhandled error | Inspect errors and use expect/filter/satisfy intentionally |
| @GraphQlTest cannot find service | Slice test does not scan service beans | Use @MockitoBean or @Import |
| documentName cannot find file | File is not under graphql-test/ or wrong name | Check classpath and extension |
| Fragment is not recognized | Fragment was not attached to the request | Use fragment() or fragmentName() |
| HTTP tester reports status assertion failure | HTTP response is not 200 | Check transport status using WebTestClient |
| Test depends on data ordering | Assertion relies on unstable list positions | Assert by ID or set conditions |
| Subscription test receives only one response | Used execute() or publisher completed early | Use executeSubscription() and check the event source |

## 23. Checklist for Writing Execute Query Tests

Before finishing tests for a Query:

- [ ] The GraphQL document is valid against the schema.
- [ ] Variables and operationName are passed properly.
- [ ] The Query is executed using execute().
- [ ] Paths are evaluated relative to data.
- [ ] Scalars, objects, or lists are decoded into the right types.
- [ ] Assertions only check fields relevant to the behavior under verification.
- [ ] GraphQL errors are checked and not unintentionally ignored.
- [ ] Partial data and null propagation are verified when needed.
- [ ] Missing-data cases have dedicated tests.
- [ ] Tests verify the service receives the right arguments.
- [ ] Document files and fragments load properly if used.
- [ ] Slice test vs. HTTP integration test is chosen according to scope.
- [ ] Use executeSubscription() for Subscriptions instead of execute().
- [ ] Do not call subscribe() manually to trigger query tests.

## Conclusion

GraphQlTester provides a unified workflow for executing GraphQL queries in tests. Tests build a request with a document, pass an operation name and variables, call execute(), and then use JsonPath to select data and map it to Java objects.

When verifying responses, check both data and errors. executeAndVerify() fits when you only need to ensure the response has no errors; execute() fits when you need to inspect fields, lists, partial data, or error paths. Combining @GraphQlTest for controller slice tests and HttpGraphQlTester for HTTP integration tests verifies the exact behavioral layers your application needs to protect.

## References

- [Spring for GraphQL — Testing and GraphQlTester](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring Boot — Auto-configured Spring GraphQL Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [GraphQlTester API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/test/tester/GraphQlTester.html)
- [GraphQlTester.Request API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/test/tester/GraphQlTester.Request.html)
- [Spring GraphQL Server Guide](https://spring.io/guides/gs/graphql-server)
