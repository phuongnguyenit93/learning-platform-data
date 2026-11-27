# Required Arguments in GraphQL and Spring for GraphQL

In GraphQL, an argument is considered required when its type is **Non-Null** (marked with `!`) and it has no default value. This rule is declared directly in the schema SDL, so GraphQL can reject requests that omit the argument or pass `null` before invoking the resolver.

Spring for GraphQL uses the validated schema to bind valid values to Java parameters with `@Argument`. This makes the API signature clearly state what data clients must supply, while helping the server catch invalid requests right at the validation and input coercion stage.

## 1. What is a required argument?

GraphQL distinguishes between nullable and non-null types:

- `String` allows a `null` value.
- `String!` does not allow a `null` value.
- `ID!` requires a non-null ID value.
- `[ID!]!` requires a non-null list and every element in the list must also be non-null.

Example schema declaring a query to find a book:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
~~~

`id: ID!` is a required argument. The client must provide `id` and cannot pass `null`. The return type `Book` does not have `!`, so the query can still return `null` if no book is found. Argument nullability and result nullability are two independent contracts.

GraphQL defines an argument as a *required argument* when the argument has a Non-Null type and no default value. Therefore, the `!` symbol is the primary indicator, but when reading a schema you must also check whether the argument has a default value.

## 2. Missing an argument and passing null are two different cases

With the declaration `book(id: ID!)`, both of the following requests are invalid.

**Missing argument:**

~~~graphql
query {
    book {
        id
        title
    }
}
~~~

**Passing null:**

~~~graphql
query {
    book(id: null) {
        id
        title
    }
}
~~~

The first case does not supply the argument. The second case supplies the argument, but its value is `null`. Both violate the Non-Null contract, so GraphQL returns a request error and does not call the `book` resolver.

If the argument is nullable, these two cases can be distinguished:

~~~graphql
type Query {
    books(keyword: String): [Book!]!
}
~~~

With `keyword: String`, the client can omit the argument or pass `null`. The server can apply distinct rules for each situation, such as not filtering when no keyword is provided. If business logic needs to clearly distinguish "condition not sent" from "null sent," design the input and handling rules intentionally.

## 3. Declaring required arguments in SDL

### 3.1. Simple arguments

Scalars commonly used as required arguments include `ID!`, `String!`, `Int!`, `Float!`, and `Boolean!`:

~~~graphql
type Query {
    book(id: ID!): Book
    books(first: Int!, published: Boolean!): [Book!]!
}
~~~

The client must pass both `first` and `published` when calling `books`. The Boolean value `false` is still a valid value; Non-Null only forbids `null`, not requiring the value to be `true` or different from Java's default value.

Similarly, `String!` still accepts an empty string `""`. The `!` mark only checks nullability; it does not check whether a string has content, whether a number is within a business range, or whether an ID exists in the database.

### 3.2. Input object arguments

When an operation needs multiple pieces of data, group the values into an input object. Example mutation to create a book:

~~~graphql
input CreateBookInput {
    title: String!
    authorId: ID!
    subtitle: String
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
}
~~~

There are two levels of requirement:

1. `input: CreateBookInput!` requires the client to pass an input object.
2. Inside the object, `title` and `authorId` are also required because they have Non-Null types and no default values.

`subtitle: String` is nullable, so the client can omit it or pass `null`. If an object is passed without `title` or `authorId`, input coercion fails and the mutation resolver is not called.

Valid example:

~~~graphql
mutation CreateBook {
    createBook(input: {
        title: "GraphQL in Practice"
        authorId: "author-12"
    }) {
        id
        title
    }
}
~~~

Invalid example because `authorId` is missing:

~~~graphql
mutation CreateBook {
    createBook(input: {
        title: "GraphQL in Practice"
    }) {
        id
    }
}
~~~

Input objects give the API a clear structure and make it easy to evolve. When adding a new field, consider compatibility with existing clients; adding a Non-Null field without a default to an input object already in use can break older requests.

### 3.3. List arguments

GraphQL allows enforcing nullability at both the list level and the element level:

| Type | Meaning |
| --- | --- |
| `[ID]` | List can be null, elements can be null |
| `[ID!]` | List can be null, elements cannot be null |
| `[ID]!` | List cannot be null, elements can be null |
| `[ID!]!` | List cannot be null, elements cannot be null |

Example:

~~~graphql
type Query {
    booksByIds(ids: [ID!]!): [Book!]!
}
~~~

The client must send a non-null list. An empty list `[]` is valid, but a list containing a null element is invalid. If business logic requires the list to contain at least one ID, validate that condition at the validation or service layer; `[ID!]!` does not enforce a minimum size on its own.

## 4. Default values and the meaning of !

A Non-Null argument with a default value is no longer a *required argument* as defined by GraphQL. The client can omit the argument and the server uses the default value. However, if the client explicitly passes `null`, the request is still invalid.

~~~graphql
type Query {
    books(first: Int! = 20): [Book!]!
}
~~~

With this declaration:

- `books` without `first`: GraphQL uses the value `20`.
- `books(first: 5)`: GraphQL uses the value `5`.
- `books(first: null)`: GraphQL rejects the request because `Int!` does not accept null.

Therefore, if the business requirement is that the client must always provide a value, do not declare a default value on the Non-Null argument.

Input object fields can also have defaults:

~~~graphql
input BookSearchInput {
    keyword: String!
    page: Int! = 1
    pageSize: Int! = 20
}
~~~

`keyword` is a required field; `page` and `pageSize` can be omitted because they have defaults. If the client passes `page: null`, the request still fails.

## 5. Required arguments when using GraphQL variables

In real-world applications, clients usually separate values from the GraphQL document using variables. A variable's type must be compatible with the argument position where it is used.

~~~graphql
query FindBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
~~~

Valid request sending variables:

~~~json
{
    "query": "query FindBook($id: ID!) { book(id: $id) { id title } }",
    "operationName": "FindBook",
    "variables": {
        "id": "book-101"
    }
}
~~~

If the `variables` object does not have the `id` key, the Non-Null variable without a default is missing and the operation cannot execute. If `"id": null` is sent, input coercion also fails. In both cases, the resolver is not called.

### 5.1. Default values of variables

A variable can also have a default value:

~~~graphql
query FindBook($id: ID! = "book-101") {
    book(id: $id) {
        id
        title
    }
}
~~~

In this case, the client can omit the `id` variable and GraphQL uses the default `book-101`. An explicitly passed `null` value is still invalid. Distinguish a variable default from a default declared on an argument in the schema; both can supply a value when the client omits one, but they belong to two different places in the contract.

### 5.2. Variables must be compatible with arguments

When an argument requires `ID!`, a `$id: ID!` variable is the direct and explicit choice. A nullable variable `$id: ID` cannot be arbitrarily used in a Non-Null position because GraphQL cannot guarantee it is non-null at execution time. Certain cases with a default on the variable or on the argument may satisfy GraphQL's compatibility rules, but you should not rely on that exception when the goal is to represent a required value. Declare a Non-Null variable when the client must provide a value.

## 6. Spring for GraphQL binds required arguments with @Argument

Spring for GraphQL maps arguments from a GraphQL field to method parameters via `@Argument`. The schema is responsible for determining whether a request is valid; `@Argument` performs binding of the value already accepted by GraphQL.

Example resolver for the `book(id: ID!)` query:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id).orElse(null);
    }
}
~~~

`@Argument("id")` extracts the exact argument named `id`. For a required argument, GraphQL has already checked the value before calling the method, so the resolver receives a value that is valid according to the GraphQL type. There is no need to repeat null checks merely to compensate for a schema that already properly declares Non-Null; you still need to check other business rules such as whether the ID exists or whether the user has access permission.

### 6.1. Binding input objects into Java records

For a mutation accepting `CreateBookInput!`, you can bind into a Java record:

~~~java
public record CreateBookInput(
        String title,
        String authorId,
        String subtitle
) {}
~~~

~~~java
import jakarta.validation.Valid;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public Book createBook(
            @Argument("input") @Valid CreateBookInput input
    ) {
        return bookService.create(input);
    }
}
~~~

Spring converts the input object into `CreateBookInput`. GraphQL has already verified that `input`, `title`, and `authorId` are present and non-null according to the SDL. `@Valid` can also be used to run Bean Validation if the application has a Jakarta Validation provider and corresponding constraints.

### 6.2. Non-Null does not replace Bean Validation

SDL `title: String!` only guarantees that the value is not null. If you want to reject empty or whitespace-only strings, declare constraints in Java:

~~~java
import jakarta.validation.constraints.NotBlank;

public record CreateBookInput(
        @NotBlank String title,
        @NotBlank String authorId,
        String subtitle
) {}
~~~

The two validation layers solve two different problems:

| Layer | Example checks |
| --- | --- |
| GraphQL schema and input coercion | Was the required argument provided? Is the value null? Is the type correct? |
| Bean Validation | Is the string empty? Is the number within the allowed range? Does the field obey application constraints? |
| Service/domain | Does the author exist? Does the user have permission to create a book? Are business rules satisfied? |

Do not rely on SDL to validate every business rule. Conversely, do not wait until the service layer to discover that a required argument is missing, since the schema can express that clearly.

## 7. How does GraphQL handle required argument errors?

GraphQL validates the document, arguments, and variables before executing resolvers. If a request omits a Non-Null argument, passes `null` into a Non-Null position, or omits a required field in an input object, GraphQL produces a request error.

For example, the client sends:

~~~graphql
query {
    book(id: null) {
        id
    }
}
~~~

The response will contain `errors` describing the Non-Null argument violation. Because the error occurs before execution, GraphQL does not call `BookController.book(...)`; this is not an error originating from the service or database.

This differs from the case where the resolver runs successfully but does not find a book. With the schema `book(id: ID!): Book`, the resolver can return `null` for a non-existent result and the response has `data.book: null`. The argument is still valid; only the business result is that no data was found.

If a resolver returns null for an output field declared Non-Null, GraphQL produces an execution error and applies null propagation up to the nearest nullable parent field. Do not confuse this error with a request error caused by the client omitting a required argument.

## 8. Testing required arguments with GraphQlTester

You should test both valid requests and cases with missing arguments or `null` values. Example with `GraphQlTester` in Spring for GraphQL tests:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

@GraphQlTest(BookController.class)
class RequiredArgumentTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @BeforeEach
    void setUp() {
        given(bookService.findById("book-101"))
                .willReturn(Optional.of(new Book("book-101", "GraphQL in Practice")));
    }

    @Test
    void acceptsRequiredId() {
        graphQlTester.document("""
                query FindBook($id: ID!) {
                    book(id: $id) {
                        id
                    }
                }
                """)
            .variable("id", "book-101")
            .execute()
            .path("book.id")
            .entity(String.class)
            .isEqualTo("book-101");
    }

    @Test
    void rejectsMissingRequiredVariable() {
        graphQlTester.document("""
                query FindBook($id: ID!) {
                    book(id: $id) {
                        id
                    }
                }
                """)
            .execute()
            .errors()
            .satisfy(errors -> assertThat(errors).isNotEmpty());
    }

    @Test
    void rejectsNullRequiredVariable() {
        graphQlTester.document("""
                query FindBook($id: ID!) {
                    book(id: $id) {
                        id
                    }
                }
                """)
            .variable("id", null)
            .execute()
            .errors()
            .satisfy(errors -> assertThat(errors).isNotEmpty());
    }
}
~~~

The example assumes `BookController` is in the GraphQL test slice and the service is configured or mocked to return a book with ID `book-101`. The error tests confirm that the request is rejected at the GraphQL layer; if you need to prove the resolver was not invoked, you can verify that the mock service had no corresponding interactions.

Additional tests should cover these scenarios:

1. Missing an argument directly on the field, e.g. `{ book { id } }`.
2. Passing `null` directly to a Non-Null argument.
3. Missing a Non-Null variable in the `variables` map.
4. Passing `null` to a Non-Null variable.
5. An input object missing a Non-Null field or passing `null` for that field.
6. A Non-Null argument with a default value: omitting it succeeds, while passing `null` is rejected.
7. A non-null value that violates Bean Validation or business rules.

## 9. API design when adding a required argument

Adding a required argument to a field already used by clients is a potentially breaking change. Older clients that do not yet send the new argument will be rejected by GraphQL before the resolver runs.

Old API example:

~~~graphql
type Query {
    books: [Book!]!
}
~~~

If changed to:

~~~graphql
type Query {
    books(tenantId: ID!): [Book!]!
}
~~~

every client calling `books` must be updated to pass `tenantId`. Before making the change, consider:

- Can the tenant be obtained from the authenticated principal or `GraphQLContext` instead of requiring the client to pass it?
- Can a nullable argument be added during a transition period with clearly defined behavior when no value is present?
- Is there a safe, business-valid default value for all clients?
- Have all clients, mobile apps, and external integrations been updated?

Do not set an arbitrary default value just to avoid compatibility errors. Default values must have clear business meaning and must not leak data across tenants or bypass security rules.

## 10. Key takeaways

- A required argument is Non-Null and has no default value.
- Missing an argument and passing `null` are two different errors, both of which violate Non-Null.
- An input object can contain multiple required fields; each field is checked according to its own type and default.
- Non-Null does not imply a non-empty string, a number in a valid range, or an existing ID.
- GraphQL validates the request before calling the resolver; `@Argument` binds the validated value into Java.
- Bean Validation and services continue to enforce constraints and business rules.
- Adding a required argument to a published schema can break existing clients.

## References

- [GraphQL Specification — Required Arguments](https://spec.graphql.org/October2021/#sec-Required-Arguments)
- [GraphQL Specification — Non-Null](https://spec.graphql.org/October2021/#sec-Non-Null)
- [GraphQL Specification — Input Objects](https://spec.graphql.org/October2021/#sec-Input-Objects)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
