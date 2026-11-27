# Testing Argument Binding

GraphQL resolvers receive input data through arguments. Spring for GraphQL converts values validated and coerced by GraphQL into Java parameters using `@Argument`, `@Arguments`, and its argument binding mechanism. A good test verifies both sides: the GraphQL document complies with the schema, and the resolver receives the exact Java values expected by the application.

Argument binding can fail at multiple layers. GraphQL can reject a document for missing a required argument or passing the wrong scalar; Spring can fail to bind an input object into a DTO; Bean Validation can detect invalid data; or the resolver can run successfully while receiving the wrong field due to mismatched mapping names. Using `GraphQlTester` with realistic documents and variables lets you verify these cases through GraphQL execution.

## 1. How Do Arguments Flow from GraphQL to Java?

Example schema:

~~~graphql
type Query {
    bookById(id: ID!): Book
}
~~~

Resolver:

~~~java
@QueryMapping
public Book bookById(@Argument("id") String id) {
    return bookService.findById(id);
}
~~~

When a client sends:

~~~graphql
query BookById($id: ID!) {
    bookById(id: $id) {
        id
        title
    }
}
~~~

The GraphQL engine parses and validates the document, checks the `id` variable, and performs coercion according to the `ID` scalar. Spring for GraphQL binds the `id` argument to the Java parameter annotated with `@Argument("id")`. Only then is the resolver invoked.

Overall flow:

~~~mermaid
flowchart TD
    A[GraphQL document + variables] --> B[Parse and validate]
    B --> C[Coerce arguments against schema]
    C --> D[Spring GraphQlArgumentBinder]
    D --> E[Bind to Java parameter / DTO]
    E --> F{Binding succeeded?}
    F -->|Yes| G[Invoke controller method]
    F -->|No| H[Binding error]
    G --> I[Resolver and service]
    H --> J[GraphQL error response]
~~~

Schema validation and coercion happen before resolvers run. Therefore, errors such as a missing `ID!` argument or passing an object to an `Int` argument are normally not exceptions thrown by the service.

## 2. Creating a GraphQlTester for Argument Binding Tests

To test binding alongside the schema and controller, you can use `ExecutionGraphQlServiceTester`:

~~~java
@SpringBootTest
class BookArgumentBindingTests {

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

This tester executes the GraphQL service directly without going through HTTP transport. It is well suited for testing documents, schema, argument binding, and resolvers.

If you need to verify HTTP security filters, headers, or request transport, use `HttpGraphQlTester` via `WebTestClient`. Tests at the GraphQL service level do not prove that the HTTP layer processed the request properly.

## 3. Testing a Scalar Argument with Document and Variable

Use GraphQL variables to pass input data instead of concatenating strings into the document:

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

This test verifies the document, variable declaration, argument mapping, and response. If the resolver uses the wrong argument name, the test fails even though calling the service directly might still work.

When testing multiple values for the same operation, you can reuse the document and swap variables:

~~~java
graphQlTester.documentName("book-by-id")
    .variable("id", "book-01")
    .execute()
    .path("bookById.id")
    .entity(String.class)
    .isEqualTo("book-01");

graphQlTester.documentName("book-by-id")
    .variable("id", "book-02")
    .execute()
    .path("bookById.id")
    .entity(String.class)
    .isEqualTo("book-02");
~~~

Document resources are placed according to the tester's document source, typically under `src/test/resources/graphql-test/` with the `.graphql` extension. `documentName()` is helpful when an operation is reused across many tests; `document()` is convenient for short operations kept inline in a test.

## 4. Verifying Scalar Types and Coercion

The GraphQL schema defines scalars for arguments. Common built-in scalars:

| GraphQL Scalar | Meaning | Common Java Type |
| --- | --- | --- |
| `String` | Character string | `String` |
| `Int` | Signed 32-bit integer | `Integer` |
| `Float` | Floating-point number | `Double` |
| `Boolean` | True/false value | `Boolean` or `boolean` |
| `ID` | Identifier | Usually `String`; can convert to other types if configured |

Example schema:

~~~graphql
type Query {
    booksByPage(page: Int!, pageSize: Int = 20): [Book!]!
}
~~~

Resolver:

~~~java
@QueryMapping
public List<Book> booksByPage(
        @Argument("page") Integer page,
        @Argument("pageSize") Integer pageSize) {
    return bookService.findPage(page, pageSize);
}
~~~

Test passing variables:

~~~java
graphQlTester.document("""
        query BooksByPage($page: Int!, $pageSize: Int) {
            booksByPage(page: $page, pageSize: $pageSize) {
                id
            }
        }
        """)
    .variable("page", 0)
    .variable("pageSize", 10)
    .execute()
    .path("booksByPage")
    .entityList(BookView.class)
    .hasSize(10);
~~~

`Int` in GraphQL has a 32-bit range. If an application needs larger integers, do not assume GraphQL `Int` automatically maps to `Long`; design a custom scalar or represent it according to an appropriate contract.

GraphQL `ID` carries identifier semantics and is typically serialized as a string. If a Java resolver uses `UUID`, verify that conversion is supported by the application configuration and include tests for both valid and invalid values.

## 5. Testing Enum Arguments

A GraphQL enum is a set of values defined in the schema. Enum literals in a document are not wrapped in quotes:

~~~graphql
enum BookStatus {
    DRAFT
    PUBLISHED
    ARCHIVED
}

type Query {
    booksByStatus(status: BookStatus!): [Book!]!
}
~~~

Resolver:

~~~java
@QueryMapping
public List<Book> booksByStatus(@Argument("status") BookStatus status) {
    return bookService.findByStatus(status);
}
~~~

The Java enum can use matching constant names:

~~~java
public enum BookStatus {
    DRAFT,
    PUBLISHED,
    ARCHIVED
}
~~~

Test using a variable:

~~~java
graphQlTester.document("""
        query BooksByStatus($status: BookStatus!) {
            booksByStatus(status: $status) {
                id
                status
            }
        }
        """)
    .variable("status", "PUBLISHED")
    .execute()
    .errors()
    .verify();
~~~

If an enum value does not exist in the schema, GraphQL rejects the input before calling the resolver. This is a coercion/validation error, not a business exception from the service.

## 6. Testing Input Object Binding to a DTO

Input objects group related arguments into a single structure:

~~~graphql
input BookFilterInput {
    keyword: String
    status: BookStatus
    minRating: Int
}

type Query {
    searchBooks(filter: BookFilterInput): [Book!]!
}
~~~

Java DTO:

~~~java
public record BookFilterInput(
        String keyword,
        BookStatus status,
        Integer minRating) {
}
~~~

Controller:

~~~java
@QueryMapping
public List<Book> searchBooks(
        @Argument("filter") BookFilterInput filter) {
    return bookService.search(filter);
}
~~~

Test:

~~~java
Map<String, Object> filter = Map.of(
    "keyword", "spring",
    "status", "PUBLISHED",
    "minRating", 4);

graphQlTester.document("""
        query SearchBooks($filter: BookFilterInput) {
            searchBooks(filter: $filter) {
                id
                title
            }
        }
        """)
    .variable("filter", filter)
    .execute()
    .path("searchBooks")
    .entityList(BookView.class)
    .hasSize(2);
~~~

Tests can be extended to verify that each individual property bound properly. When you need to verify the exact object passed to the service, use a mock or spy and an `ArgumentCaptor` to inspect `BookFilterInput`.

## 7. Constructor Binding and Property Binding

Spring for GraphQL uses its argument binder mechanism to convert a Map of GraphQL data into Java objects. Binding can rely on constructors or property access depending on the object type.

Commonly supported types:

- Java records with a canonical constructor.
- DTOs with a matching constructor.
- Mutable DTOs with setters or writable properties.
- Kotlin data classes if the application uses Kotlin with corresponding configuration.

Record example:

~~~java
public record CreateBookInput(
        String title,
        String description,
        BookStatus status) {
}
~~~

Mutable DTO example:

~~~java
public class CreateBookInput {

    private String title;
    private String description;

    public CreateBookInput() {
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }
}
~~~

When binding fails, check GraphQL field names, record component/constructor parameter names, setters, data types, and the conversion service. Do not rename schema fields just to mask a Java binding issue; first determine which input contract is the public API and which mapping needs adjustment.

## 8. Testing Nested Input Objects and Lists

GraphQL input objects can contain other objects or lists:

~~~graphql
input AddressInput {
    street: String!
    city: String!
    postalCode: String
}

input CreateAuthorInput {
    name: String!
    address: AddressInput!
    tags: [String!]!
}

type Mutation {
    createAuthor(input: CreateAuthorInput!): Author
}
~~~

Java DTOs:

~~~java
public record AddressInput(
        String street,
        String city,
        String postalCode) {
}

public record CreateAuthorInput(
        String name,
        AddressInput address,
        List<String> tags) {
}
~~~

Test:

~~~java
Map<String, Object> input = Map.of(
    "name", "Mai",
    "address", Map.of(
        "street", "12 Nguyen Hue",
        "city", "Ho Chi Minh City",
        "postalCode", "700000"),
    "tags", List.of("java", "graphql"));

graphQlTester.document("""
        mutation CreateAuthor($input: CreateAuthorInput!) {
            createAuthor(input: $input) {
                id
                name
                address {
                    city
                }
            }
        }
        """)
    .variable("input", input)
    .execute()
    .path("createAuthor.address.city")
    .entity(String.class)
    .isEqualTo("Ho Chi Minh City");
~~~

This test verifies that nested maps bind into nested DTOs and lists convert properly. For complex inputs, include assertions for key fields rather than checking only the response ID.

## 9. @Argument and @Arguments

`@Argument` binds a specific GraphQL argument to a method parameter:

~~~java
@QueryMapping
public List<Book> books(
        @Argument("keyword") String keyword,
        @Argument("status") BookStatus status) {
    return bookService.search(keyword, status);
}
~~~

`@Arguments` binds all arguments of a field into an object or Map:

~~~java
public record BookSearchArguments(
        String keyword,
        BookStatus status,
        Integer page) {
}

@QueryMapping
public List<Book> books(@Arguments BookSearchArguments arguments) {
    return bookService.search(arguments);
}
~~~

When using `@Arguments`, DTO property names must match argument names in the schema. Tests should pass multiple arguments together to confirm the whole object binds, and include a test where an optional argument is omitted.

Maps are flexible but lose compile-time type checking. DTOs/records catch mapping mistakes earlier and make the contract received by the resolver explicit.

## 10. Distinguishing Omitted Arguments from Explicit Null

For nullable arguments, GraphQL distinguishes two cases:

- The client does not send the argument.
- The client sends the argument with value `null`.

In some update mutations, the two cases carry different meanings. For example, omitting `description` means keeping the existing value; sending `description: null` means clearing the description.

If the method directly takes `String`, both cases become `null` and the application can no longer distinguish them. Spring for GraphQL provides `ArgumentValue<T>` to preserve the omitted state:

~~~java
@MutationMapping
public Book updateBook(
        @Argument("id") String id,
        @Argument("description") ArgumentValue<String> description) {

    if (description.isOmitted()) {
        return bookService.keepDescription(id);
    }

    if (description.value() == null) {
        return bookService.clearDescription(id);
    }

    return bookService.changeDescription(id, description.value());
}
~~~

Tests must verify all three states separately:

~~~java
// 1. Argument omitted: do not call variable("description", ...).
graphQlTester.document(UPDATE_BOOK)
    .variable("id", "book-01")
    .execute();

// 2. Explicit null: variable is present with value null.
graphQlTester.document(UPDATE_BOOK)
    .variable("id", "book-01")
    .variable("description", null)
    .execute();

// 3. With a value.
graphQlTester.document(UPDATE_BOOK)
    .variable("id", "book-01")
    .variable("description", "Updated description")
    .execute();
~~~

These are three separate requests. In real tests, assert the result or verify that the service receives the corresponding `ArgumentValue` state.

If the schema declares a default value for an argument, GraphQL may apply the default before the binder receives the value. When business logic needs to distinguish omitted from explicit null, avoid defining a default that erases that difference; instead handle defaults in the application layer or test the exact desired semantics.

## 11. Testing Default Values

A schema can define defaults for arguments or input fields:

~~~graphql
type Query {
    books(page: Int = 0, size: Int = 20): [Book!]!
}
~~~

When a client omits `page` and `size`, GraphQL applies the defaults from the schema. Tests should cover both omitting them and passing different values:

~~~java
graphQlTester.document("""
        query {
            books {
                id
            }
        }
        """)
    .execute()
    .errors()
    .verify();

graphQlTester.document("""
        query Books($page: Int, $size: Int) {
            books(page: $page, size: $size) {
                id
            }
        }
        """)
    .variable("page", 2)
    .variable("size", 5)
    .execute()
    .errors()
    .verify();
~~~

To confirm the resolver actually received page 0 and size 20 in the first case, verify the service call or check the result count and contents. Do not only verify zero errors, as that alone does not prove defaults were bound properly.

## 12. Testing Required Arguments and Nullability

GraphQL schemas use `!` to mark an argument or input field as non-null:

~~~graphql
type Query {
    bookById(id: ID!): Book
}
~~~

Cases to test:

| Input | Expected Outcome |
| --- | --- |
| `id` omitted | GraphQL request/validation error |
| `id = null` passed | GraphQL coercion/validation error |
| Validly typed `id` passed | Resolver is invoked |
| Object passed instead of `ID` | GraphQL coercion error |

Example checking a missing variable:

~~~java
var response = graphQlTester.document("""
        query BookById($id: ID!) {
            bookById(id: $id) {
                id
            }
        }
        """)
    .execute();

response.errors().satisfy(errors ->
    assertThat(errors).isNotEmpty());
~~~

This test omits the `id` variable, so GraphQL cannot execute an operation with a required variable. Verify that the service is not called if the test mocks/spies on the service.

Missing required argument errors occur before the resolver. Do not expect `DataFetcherExceptionResolver` to handle this error because the DataFetcher has not run yet.

## 13. Testing Input Binding Failures and Bean Validation

Two error categories are easily confused:

- **GraphQL coercion/validation:** wrong scalar, missing non-null field, nonexistent enum value, or an input object with a field not declared in the schema.
- **Java binding/Bean Validation:** data valid per the GraphQL schema that fails to bind to a Java type or violates application-layer constraints.

For example, the schema allows any string:

~~~graphql
input CreateBookInput {
    title: String!
}
~~~

However, the DTO or domain requires title not to be blank. GraphQL accepts an empty string because it is still a String; Bean Validation/domain validation decides that value is invalid.

DTO:

~~~java
public record CreateBookInput(
        @NotBlank String title) {
}
~~~

Resolver:

~~~java
@MutationMapping
public Book createBook(@Argument("input") @Valid CreateBookInput input) {
    return bookService.create(input);
}
~~~

Tests should verify:

- A valid string binds and the service receives the expected DTO.
- A blank string passes GraphQL coercion but is rejected by validation.
- A wrongly typed input is rejected by GraphQL before the resolver.
- Error codes/messages are returned per the application's contract.

Depending on Spring configuration and version, binding/validation exceptions may be handled via `BindingResult`, `DataFetcherExceptionResolver`, or `@GraphQlExceptionHandler`. Tests should verify the actual response rather than assuming all errors share the same shape.

## 14. BindingResult and Handling Binding Errors

When binding errors need to be handled in a controller, Spring for GraphQL supports an `Errors` or `BindingResult` parameter placed immediately after the corresponding bound parameter in supported cases:

~~~java
@MutationMapping
public Book createBook(
        @Argument("input") @Valid CreateBookInput input,
        BindingResult errors) {

    if (errors.hasErrors()) {
        throw new BindException(errors);
    }
    return bookService.create(input);
}
~~~

This snippet illustrates how a controller forwards binding errors to an application error. Check the binding API and exception types of your Spring for GraphQL version; avoid accepting a BindingResult, ignoring its errors, and proceeding with side effects.

In tests, send an input with an invalid field to verify that the resolver writes no data and the response contains standardized validation errors. If an error occurs before the controller method is invoked, BindingResult cannot handle GraphQL parse/coercion errors.

## 15. Testing Custom Scalars

Applications can define custom scalars such as `Date`, `DateTime`, `UUID`, or `Money`. In such cases, tests should verify that both literals and variables are coerced properly by the scalar implementation.

Example schema using a Date scalar:

~~~graphql
scalar Date

input PublicationFilter {
    publishedAfter: Date
}

type Query {
    books(filter: PublicationFilter): [Book!]!
}
~~~

If the scalar is configured to accept ISO date strings, test passing a variable:

~~~java
Map<String, Object> filter = Map.of(
    "publishedAfter", "2026-01-01");

graphQlTester.document("""
        query Books($filter: PublicationFilter) {
            books(filter: $filter) {
                id
            }
        }
        """)
    .variable("filter", filter)
    .execute()
    .errors()
    .verify();
~~~

Also test a malformed value to confirm the scalar rejects the input during coercion and the resolver does not run. Exact format rules must follow the custom scalar's contract; do not assume every Date scalar uses the same format.

## 16. Testing Unknown Input Fields

GraphQL input objects only accept fields declared by the schema. For example, if `CreateBookInput` has no `ownerId` field, a client sending that extra field must be rejected:

~~~graphql
mutation {
    createBook(input: {
        title: "Spring GraphQL"
        ownerId: "user-02"
    }) {
        id
    }
}
~~~

This is a GraphQL validation/coercion error before the resolver runs. Tests should verify:

- The response contains errors.
- The create service is not invoked.
- No new data is persisted.

This check helps detect unintended expansion of the schema input contract or clients sending unsupported fields. However, do not treat schema rejection of `ownerId` as the sole authorization layer; services must still assign owner from the authenticated principal.

## 17. Verifying the Service Receives the Right Arguments

Checking the response verifies the final output, while sometimes you need to confirm the resolver passed the exact data into the service. Use a mock and an argument captor:

~~~java
@Captor
ArgumentCaptor<BookFilterInput> filterCaptor;

// After executing the GraphQL operation:
verify(bookService).search(filterCaptor.capture());

assertThat(filterCaptor.getValue().keyword()).isEqualTo("spring");
assertThat(filterCaptor.getValue().status()).isEqualTo(BookStatus.PUBLISHED);
assertThat(filterCaptor.getValue().minRating()).isEqualTo(4);
~~~

This example assumes the test configured a mock `bookService` and injected the captor via Mockito. In integration tests using a real repository, verify query results and persistence state instead of capturing calls.

Do not mock everything in every test. Mocks are useful for checking resolver mapping and that inputs are forwarded properly; integration tests with real services/repositories are necessary to verify conversion, queries, and transactions.

## 18. Testing Multiple Arguments and Aliases

A field can accept multiple arguments:

~~~graphql
type Query {
    searchBooks(keyword: String, status: BookStatus, page: Int): [Book!]!
}
~~~

Resolver:

~~~java
@QueryMapping
public List<Book> searchBooks(
        @Argument("keyword") String keyword,
        @Argument("status") BookStatus status,
        @Argument("page") Integer page) {
    return bookService.search(keyword, status, page);
}
~~~

Tests should pass all arguments, omit nullable arguments, and pass explicit nulls to confirm each parameter binds as expected.

GraphQL also allows calling the same field multiple times using aliases:

~~~graphql
query {
    published: searchBooks(status: PUBLISHED) {
        id
    }
    drafts: searchBooks(status: DRAFT) {
        id
    }
}
~~~

Two aliases trigger two resolutions with different arguments. Tests should confirm each branch receives the right enum and responses appear under the matching aliases. This also catches resolvers accidentally sharing mutable state across invocations.

## 19. Important Assertions for Argument Binding

A practical test suite should cover these categories:

| Category | Cases |
| --- | --- |
| Scalar | Valid and wrongly typed String, Int, Float, Boolean, ID |
| Enum | Valid enum, nonexistent enum |
| Input object | Simple DTO/record and nested objects |
| List | Scalar list, input object list, null elements if schema allows |
| Required | Omitted argument or passing null for non-null |
| Optional | Omitted argument, explicit null, and concrete value |
| Default | Omitting argument with default and passing an override value |
| Binding | Field names, constructor/property, conversion |
| Validation | Bean Validation and domain constraints |
| Custom scalar | Valid and malformed literals/variables |
| Security | ID/tenant argument not belonging to principal |
| Side effect | Mutation does not execute when input/binding/authorization fails |

You do not need one giant test for every case. Splitting by contract and behavior makes failures easier to pinpoint.

## 20. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Java parameter is always null | `@Argument` name does not match schema argument name | Specify `@Argument("...")` explicitly and test with real documents |
| Input DTO fails to bind | Constructor/property or field names mismatch | Check record components, constructors, and setters |
| Enum fails to convert to Java enum | Value does not match schema/Java enum | Use exact enum tokens and mapping |
| ID fails to convert to UUID | Missing appropriate conversion | Use String or register explicit conversion/scalar |
| Cannot distinguish omitted from null | Using regular nullable parameter | Use `ArgumentValue<T>` |
| Default value differs from expectation | Confusing schema default with Java default | Check schema default and test the omitted case |
| Resolver does not run on bad input | GraphQL coercion/validation rejects before execution | Assert request errors and verify service was not called |
| Bean Validation does not run | Missing `@Valid` or proper validation configuration | Check annotations and validation provider |
| Binding error returned as internal error | Exception not normalized | Use `BindingResult` or appropriate error resolver |
| Test passes yet service receives wrong object | Only checking response indirectly | Capture arguments or verify service output |
| Unknown input field still gets persisted | Input DTO/entity allows mass assignment | Use input type allowlists and explicit mapping |

## 21. Principles for Designing Argument Binding Tests

Use real GraphQL documents so requests go through parsing, validation, and coercion; pass data with variables so tests stay close to client requests. Use `@Argument` for individual arguments and `@Arguments` when binding all arguments together; for input objects, prefer DTOs/records with clear field names and test nested binding.

Separately test scalars, enums, lists, required/nullability, defaults, custom scalars, and binding/validation failures. Use `ArgumentValue<T>` when business logic needs to distinguish omitted arguments from explicit nulls. Verify that resolvers receive the right objects through response assertions or argument capture, and verify that services do not run when GraphQL rejects input before execution.

For mutations, verify side effects and prevent inputs from setting sensitive fields like owner or tenant. For authorization, use authenticated principals and test IDs/tenants outside the caller's permissions. For errors, distinguish pre-resolver coercion/validation from DataFetcher exceptions so assertions target the right layer.

Good argument binding tests prove the contract between the schema and Java methods: client-supplied data is validated, converted, and bound to the right parameters, while invalid inputs are rejected before causing side effects in the system.
