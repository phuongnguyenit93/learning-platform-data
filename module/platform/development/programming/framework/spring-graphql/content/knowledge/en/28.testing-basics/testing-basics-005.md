# GraphQlTester document

In Spring for GraphQL, testing a GraphQL operation is not just calling a controller and checking a Java object. You need to verify that the GraphQL document is parsed and validated, arguments are bound properly, resolvers run as expected, the response has the right shape, errors are returned according to contract, and fields resolve according to the schema.

GraphQlTester is Spring for GraphQL's testing API for query, mutation, and subscription operations. A test typically starts by creating a GraphQL document, passing variables if needed, calling execute(), and then asserting the response using path, entity, and errors. This lesson focuses on using document() and documentName() to write readable, maintainable tests.

## 1. What Problem Does GraphQlTester Solve?

A resolver unit test can prove that a method returns the right value when called directly, but it does not prove that the GraphQL runtime can invoke that method properly. A GraphQL operation also passes through many stages:

1. Parse the GraphQL document.
2. Validate fields, arguments, variables, and data types against the schema.
3. Bind arguments to controller parameters.
4. Select the DataFetcher for each field.
5. Invoke resolvers and related services.
6. Resolve nested fields, DataLoaders, or batch mappings.
7. Apply nullability and error handling.
8. Serialize the response according to the GraphQL response shape.

GraphQlTester helps test the GraphQL flow at the operation level. Tests can send real documents and inspect responses as a client would see them. As a result, tests catch schema, mapping, argument binding, error path, or null propagation issues that pure Java unit tests can miss.

## 2. Types of GraphQlTester

Spring for GraphQL provides testers suited for different boundaries:

| Tester | Boundary Tested | When to Use |
| --- | --- | --- |
| ExecutionGraphQlServiceTester | In-app GraphQL service, without HTTP transport | Testing schema, resolvers, argument binding, and GraphQL execution |
| HttpGraphQlTester | HTTP endpoint via WebTestClient | Testing endpoint, HTTP headers, status, security filters, and transport |
| WebSocketGraphQlTester | WebSocket GraphQL endpoint | Testing subscriptions, connection lifecycle, and event streams |
| RSocketGraphQlTester | RSocket route | Testing GraphQL over RSocket if the application enables this transport |

All testers share the GraphQlTester API for building documents and asserting responses. The difference lies in how requests are sent to the server.

If you only need to check resolvers/schema, a tester at the ExecutionGraphQlService level is usually fast and has minimal infrastructure dependencies. If you want to verify Spring Security filters, CORS, HTTP status codes, or headers, you must test over HTTP. An in-process test cannot prove that filters or proxies outside the GraphQL service ran properly.

## 3. Creating a Tester in Tests

For an in-app GraphQL service, you can create a tester directly from the service:

~~~java
@SpringBootTest
class BookGraphQlTests {

    @Autowired
    GraphQlService graphQlService;

    GraphQlTester graphQlTester;

    @BeforeEach
    void setUp() {
        graphQlTester =
            ExecutionGraphQlServiceTester.create(graphQlService);
    }
}
~~~

This example focuses on execution and sends no HTTP requests. The Spring context is still initialized, so controllers, schema mappings, services, and related beans participate in GraphQL execution.

To test an HTTP endpoint, create a tester from WebTestClient:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BookHttpGraphQlTests {

    @Autowired
    WebTestClient webTestClient;

    HttpGraphQlTester graphQlTester;

    @BeforeEach
    void setUp() {
        graphQlTester = HttpGraphQlTester.builder(webTestClient).build();
    }
}
~~~

With test slices or custom configurations, you can inject or instantiate a tester matching that test context. Avoid recreating a new GraphQL schema or controller inside every test if the goal is to verify the real application configuration.

## 4. document() with an Inline GraphQL String

document(String) takes a GraphQL document as a string. This approach is convenient for short operations, tests focused on a single behavior, or tests where keeping the document right next to the assertion improves clarity:

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
    .entityList(BookView.class)
    .hasSize(2);
~~~

Java text blocks make multiline GraphQL readable without string concatenation. Documents in tests should select only the fields needed for the behavior under test; there is no need to copy a huge operation when a small selection set accurately expresses the goal.

Inline documents are well suited when:

- The query only has a few fields.
- The test checks a specific error.
- The document is not reused across multiple tests.
- You want to see the operation directly in the test without opening another file.

When a document is long or used in many tests, consider documentName().

## 5. documentName() with Separate GraphQL Files

documentName(String) loads a GraphQL document from a classpath resource. Under GraphQlTester's default configuration, test documents are typically placed in the graphql-test/ directory with the .graphql extension.

Example structure:

~~~text
src
  test
    resources
      graphql-test
        books.graphql
        book-by-id.graphql
        update-book.graphql
~~~

Contents of books.graphql:

~~~graphql
query Books {
    books {
        id
        title
    }
}
~~~

Test:

~~~java
graphQlTester.documentName("books")
    .execute()
    .path("books")
    .entityList(BookView.class)
    .hasSize(2);
~~~

Extracting documents into separate files offers several benefits:

- Operations closely match the documents actually used by frontends or clients.
- A single document can be reused across multiple tests with different variables.
- GraphQL files get syntax highlighting and are easier to read than long Java strings.
- When an operation changes, diffs focus purely on the document.
- Test queries, mutations, and subscriptions can be organized into groups.

Resource names are resolved according to GraphQlTester's configured document source. If the application customizes ResourceLoader or the document source, place files according to that configuration. When a document is not found, check the resource name, classpath, and file extension before investigating resolvers.

## 6. Choosing documentName or document?

| Criterion | document() | documentName() |
| --- | --- | --- |
| Where document is stored | Inside test code | Resource file on classpath |
| Suitable length | Short to medium | Medium to long |
| Reusability | Easy to duplicate across multiple tests | Same document can be reused |
| Syntax highlighting | Depends on Java editor | GraphQL editors usually support it well |
| Changing the operation | Edit string in test | Edit .graphql file |
| Variables | Passed via variable() the same way | Passed via variable() the same way |

There is no mandatory rule requiring every test to use documentName(). Using inline documents for short operations and documentName() for long or reused operations usually balances readability and maintainability.

## 7. Passing Variables and operationName

Use GraphQL variables instead of embedding values directly into the document. This keeps tests close to how real clients send requests while separating the document from test data:

~~~java
graphQlTester.document("""
        query BookById($id: ID!) {
            bookById(id: $id) {
                id
                title
            }
        }
        """)
    .operationName("BookById")
    .variable("id", "book-01")
    .execute()
    .path("bookById.id")
    .entity(String.class)
    .isEqualTo("book-01");
~~~

operationName is useful when a document contains multiple operations. The GraphQL server needs to know which operation to execute. Even if a document has only one operation, naming it clearly describes the operation under test.

With multiple variables:

~~~java
graphQlTester.documentName("search-books")
    .operationName("SearchBooks")
    .variable("keyword", "spring")
    .variable("page", 0)
    .variable("size", 10)
    .execute();
~~~

Never concatenate user input directly into a GraphQL string. Using variable() lets GraphQL handle schema coercion and avoids syntax errors caused by special characters.

## 8. Checking a Field with path()

After execute(), GraphQlTester returns a response. path(String) selects a location in data for assertions:

~~~java
graphQlTester.document("""
        query {
            bookById(id: "book-01") {
                id
                title
            }
        }
        """)
    .execute()
    .path("bookById.title")
    .entity(String.class)
    .isEqualTo("Spring for GraphQL");
~~~

Path uses the GraphQL response key, not the Java method name or repository name. If the query uses an alias, the path must use the alias.

Example:

~~~graphql
query {
    featured: bookById(id: "book-01") {
        id
        title
    }
}
~~~

The assertion must read featured.title:

~~~java
response.path("featured.title")
    .entity(String.class)
    .isEqualTo("Spring for GraphQL");
~~~

Paths can point to nested fields. When testing errors or lists, use path expressions compatible with the JSON response structure and GraphQlTester's JsonPath support.

## 9. Converting Fields into Entities

entity(Class) converts the value at the path into a Java type:

~~~java
graphQlTester.documentName("book-by-id")
    .variable("id", "book-01")
    .execute()
    .path("bookById")
    .entity(BookView.class)
    .satisfies(book -> {
        assertThat(book.id()).isEqualTo("book-01");
        assertThat(book.title()).isEqualTo("Spring for GraphQL");
    });
~~~

Test DTOs only need to contain the fields queried and asserted:

~~~java
public record BookView(String id, String title) {
}
~~~

There is no need to deserialize an entire domain entity when the response only contains a subset of data. Dedicated DTOs keep tests aligned with the GraphQL response contract and avoid accidental coupling to internal fields.

## 10. Verifying Lists

For lists, use entityList(Class) to convert elements into Java types:

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
    .entityList(BookView.class)
    .hasSize(2);
~~~

You can inspect individual elements further after converting the list:

~~~java
List<BookView> books = graphQlTester.documentName("books")
    .execute()
    .path("books")
    .entityList(BookView.class)
    .get();

assertThat(books)
    .extracting(BookView::id)
    .containsExactlyInAnyOrder("book-01", "book-02");
~~~

When list ordering is part of the contract, use an order-sensitive assertion. If ordering is not guaranteed, assert the set of IDs or stable attributes instead of making tests depend on arbitrary database order.

## 11. Verifying Null and Missing Values

GraphQL can return null for nullable fields. Use valueIsNull() when null is the expected result:

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
    .path("bookById")
    .valueIsNull();
~~~

Null can carry multiple meanings:

- The resolver returned null as business behavior.
- The field has no data.
- A nullable field failed execution.
- Null propagation from a nested non-null field.

Therefore, if null is the result of an error, verify both errors and the path rather than asserting valueIsNull() alone.

Example:

~~~java
var response = graphQlTester.documentName("book-by-id")
    .variable("id", "missing")
    .execute();

response.path("bookById").valueIsNull();
response.errors()
    .expect(error ->
        "BOOK_NOT_FOUND".equals(error.getExtensions().get("code")))
    .verify();
~~~

## 12. Verifying GraphQL Errors

GraphQlTester should not be used to assert only data while ignoring errors. A test can receive partial data alongside field errors; if errors are not checked, the test may pass even when the API violates its contract.

When an operation is expected to have no errors, call errors().verify():

~~~java
graphQlTester.documentName("books")
    .execute()
    .errors()
    .verify();
~~~

When a test intentionally verifies an error, use expect() to assert the expected error:

~~~java
var response = graphQlTester.documentName("book-by-id")
    .variable("id", "missing")
    .execute();

response.errors()
    .expect(error ->
        "BOOK_NOT_FOUND".equals(error.getExtensions().get("code")))
    .verify();
~~~

Predicates in expect() should check stable attributes like extensions.code, path, or error classification. Avoid depending on full message text if messages may be localized.

## 13. Verifying Error Paths and Extensions

GraphQL errors include a path indicating the failing response field. When clients use aliases or nested fields, the path reflects the response key:

~~~java
response.errors()
    .expect(error ->
        error.getPath().equals(List.of("featured")))
    .verify();
~~~

For nested fields, paths can contain field names and list indices. Compare the exact path structure instead of checking only the message.

Extensions are where applications expose error codes and metadata:

~~~java
response.errors()
    .expect(error ->
        "VALIDATION_FAILED".equals(error.getExtensions().get("code")))
    .verify();
~~~

If the error contract includes violations, you can assert the count and field names via extensions. Do not only assert that errors is non-empty; verify the right code and ensure rejected values or sensitive data are not leaked.

## 14. Testing Partial Data

GraphQL allows one field to fail while other fields still succeed. Tests should verify both outcomes:

~~~java
var response = graphQlTester.document("""
        query {
            bookById(id: "missing") {
                id
            }
            latestBooks {
                id
                title
            }
        }
        """)
    .execute();

response.path("latestBooks")
    .entityList(BookView.class)
    .hasSize(2);

response.path("bookById").valueIsNull();

response.errors()
    .expect(error ->
        "BOOK_NOT_FOUND".equals(error.getExtensions().get("code")))
    .verify();
~~~

This test confirms that the API does not lose data from independent fields when another field fails. If the schema declares non-null, null propagation can turn parent or root data into null; write assertions matching the actual schema.

## 15. Testing Mutations and Input Objects

Mutations commonly accept input objects. Use variables to test argument binding and validation:

~~~graphql
mutation UpdateBook($input: UpdateBookInput!) {
    updateBook(input: $input) {
        id
        title
    }
}
~~~

Test:

~~~java
Map<String, Object> input = Map.of(
    "bookId", "book-01",
    "title", "New title");

graphQlTester.documentName("update-book")
    .variable("input", input)
    .execute()
    .path("updateBook.title")
    .entity(String.class)
    .isEqualTo("New title");
~~~

Write separate tests for:

- Valid input where the mutation returns updated data.
- Missing required fields or wrong types.
- Bean/domain validation failures.
- Users lacking permission to update the resource.
- Mutations producing no side effects when validation/authorization fails.
- Inputs unable to alter owner, tenant, or role if those fields are not part of the public contract.

For mutations, checking the response alone is not enough to prove side effects are correct. Verify repositories, event publishers, or aggregate state after the operation runs. When a request is rejected, confirm that data remains unchanged.

## 16. Testing Schema Validation and Argument Coercion

GraphQlTester sends real documents through the GraphQL engine, so it can verify errors that occur before resolvers run:

- Fields that do not exist in the schema.
- Missing or wrongly typed arguments.
- Variables incompatible with a scalar.
- Invalid enum values.
- Non-null fields receiving null.

These errors differ from exceptions thrown inside a DataFetcher. Tests should verify they do not unintentionally trigger services or repositories.

For example, when passing an ID of the wrong type, GraphQL may return a request/validation error before invoking the resolver. Do not write tests expecting DataFetcherExceptionResolver to handle coercion errors, because the resolver has not executed yet.

## 17. Testing Authentication and Authorization

A tester at the GraphQL execution level can set up GraphQLContext or security context per test configuration, but it does not necessarily pass through the entire HTTP security filter chain.

If you want to verify Spring Security HTTP configuration, use HttpGraphQlTester backed by WebTestClient and send requests with appropriate test principals/tokens. Verify all of these:

- Unauthenticated requests are rejected.
- Principals with the required authority are granted access.
- Authenticated principals without permission are denied.
- User A cannot read User B's resources by changing an ID argument.
- Tenant A cannot access Tenant B's data.
- Error responses do not disclose sensitive resources.

For method security, beans must be invoked through Spring proxies in the test context. A unit test calling a manually instantiated object directly will not trigger AOP method security.

## 18. documentName and Organizing Test Documents

As the number of tests grows, group GraphQL files by feature or use case:

~~~text
src/test/resources/graphql-test/
  books/
    books.graphql
    book-by-id.graphql
    update-book.graphql
  authors/
    author-by-id.graphql
  orders/
    order-by-id.graphql
    cancel-order.graphql
~~~

The name passed to documentName depends on the resource path and configured document source. Keep names consistent and avoid multiple files with the same name in different directories if the configuration does not clearly distinguish them.

Do not store tokens, passwords, or production data inside .graphql files. Use variables in tests to pass mock fixtures. Documents should hold the operation structure; data that varies per test belongs in variable().

## 19. Testing Subscriptions

Subscriptions differ from queries/mutations because the result is an event stream. With WebSocketGraphQlTester, you can call executeSubscription() and inspect the publisher using Reactor Test StepVerifier:

~~~java
Flux<OrderEventView> events = webSocketGraphQlTester
    .documentName("order-updated")
    .variable("orderId", "order-01")
    .executeSubscription()
    .toFlux("orderUpdated", OrderEventView.class);

StepVerifier.create(events)
    .expectNextMatches(event ->
        event.orderId().equals("order-01"))
    .thenCancel()
    .verify();
~~~

Subscription tests should verify expected events, ordering if guaranteed by the contract, stream errors, cancellation, and cleanup. When testing authentication, configure credentials on the WebSocket connection or operation in the same way the real application uses them.

Do not let subscription tests wait indefinitely. Use StepVerifier with appropriate timeouts and actively cancel after receiving the required number of events. For authorization tests, verify that invalid principals cannot open the subscription or do not receive unauthorized events.

## 20. Deterministic Test Data and Isolation

GraphQL tests often fail intermittently if they rely on shared data or unguaranteed database ordering.

You should:

- Create dedicated fixture data per test or use appropriate transactions/test cleanup.
- Use readable, fixed IDs in tests.
- Avoid depending on list order if the schema does not guarantee order.
- Mock services in resolver tests when you want to verify specific mappings.
- Use real repositories/databases in integration tests when verifying queries, transactions, or persistence.
- Prevent parallel tests from writing to the same shared record.
- Verify both side effects and GraphQL responses for mutations.

Tests at the GraphQlTester level do not automatically guarantee database rollback. Test transactions depend on the test runner, transport type, and thread/reactive execution. With HTTP or async execution, verify actual transaction boundaries instead of assuming a test method transaction covers all work.

## 21. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| documentName not found | File is not on classpath or resource name is wrong | Check graphql-test path, name, and extension |
| Test passes despite response errors | errors().verify() not called or expected errors not asserted | Check errors in every test |
| Path assertion cannot find field | Used schema field name instead of alias response key | Use the exact response path |
| Entity mapping fails | DTO does not match response shape or scalar mapping | Use a DTO with matching fields and types |
| Null assertion still misses errors | Did not check errors and null propagation | Check value, error path, and schema nullability |
| Security test still allows access | Test called object directly, bypassing proxy/filters | Use Spring context and tester at the right boundary |
| HTTP security is not tested | Used ExecutionGraphQlServiceTester | Use HttpGraphQlTester via WebTestClient |
| Subscription test hangs | Did not cancel or lacked timeout | Use StepVerifier and a controllable publisher |
| Test depends on database ordering | No ordering contract or stable fixture | Sort in query or use order-independent assertions |
| Mutation test only checks response | Side effects can be wrong even when response looks right | Verify persistence/event state after the mutation |

## 22. Principles for Designing GraphQlTester Document Tests

Use document() for short operations and documentName() for long or reused documents. Pass inputs using variable() and set operationName when a document has multiple operations or to clarify test intent. Use path() to check exact response keys, entity()/entityList() to map data, and errors() to verify the error contract.

Choose the tester matching the boundary to verify: ExecutionGraphQlServiceTester for GraphQL execution, HttpGraphQlTester for HTTP/security filters, WebSocketGraphQlTester for subscriptions, and RSocketGraphQlTester when using RSocket. Do not use an in-process test to conclude that transport or proxies work properly.

For each test, clearly define whether success or failure is expected. Success tests should verify zero GraphQL errors; error tests should assert code/path and verify corresponding data/null propagation. For mutations, verify side effects; for subscriptions, verify events and cancellation. Keep fixtures deterministic so tests reflect the GraphQL API contract rather than accidental environment details.

GraphQlTester documents allow testing GraphQL like a real client interacting with the schema. When documents, variables, response paths, and errors are explicitly verified, tests become a readable contract between the schema, resolvers, and API consumers.
