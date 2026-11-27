# Enum Input

In GraphQL, an **enum** is a data type that enumerates a finite set of values permitted by the schema. When using an enum as input, clients can only send one of the declared values. This helps an API clearly express valid choices, such as order statuses, book genres, roles, or sort directions.

With Spring for GraphQL, an enum in SDL can be mapped to a Java enum so controllers and services work with strongly typed values. This lesson covers how to declare enums, pass enums through arguments and input objects, how GraphQL validates values, and what to watch out for when evolving enums in an API.

## 1. What Is an Enum in GraphQL?

An enum is declared using the `enum` keyword, followed by the type name and the list of values:

~~~graphql
enum BookGenre {
    TECHNOLOGY
    SCIENCE
    HISTORY
    FICTION
}
~~~

`BookGenre` is an enum type with four permitted values. Clients can use these values when passing arguments or fields belonging to an input object.

An enum differs from a scalar like `String` in that it restricts the set of allowed values. With a String argument, a client can send almost any string. With a BookGenre argument, only the four values defined in the schema are accepted.

Example:

~~~graphql
type Query {
    booksByGenre(genre: BookGenre!): [Book!]!
}
~~~

The `booksByGenre` field requires the `genre` argument to be non-null and belong to the BookGenre enum.

## 2. Passing Enums in GraphQL Operations

When writing an enum value directly in a GraphQL document, use the enum value name without quotes:

~~~graphql
query {
    booksByGenre(genre: TECHNOLOGY) {
        id
        title
    }
}
~~~

`TECHNOLOGY` is an enum literal. If written as a string:

~~~graphql
query {
    booksByGenre(genre: "TECHNOLOGY") {
        id
        title
    }
}
~~~

the request is invalid because `"TECHNOLOGY"` is a String literal, whereas the schema requires BookGenre. GraphQL checks the literal type before executing the resolver.

### Passing Enums via Variables

In real applications, prefer using variables to separate input data from the operation document:

~~~graphql
query BooksByGenre($genre: BookGenre!) {
    booksByGenre(genre: $genre) {
        id
        title
    }
}
~~~

Request variables are JSON:

~~~json
{
    "genre": "TECHNOLOGY"
}
~~~

Here the JSON string must have quotes according to JSON syntax. GraphQL converts that string value into the corresponding enum value based on the declared BookGenre type.

Distinguish the two syntaxes:

| Context | How to Write |
| --- | --- |
| GraphQL literal | `genre: TECHNOLOGY` |
| JSON variables | `{"genre": "TECHNOLOGY"}` |
| String literal in GraphQL | `genre: "TECHNOLOGY"` — wrong type if argument expects BookGenre |

Enum value names are case-sensitive. `TECHNOLOGY` and `technology` are two distinct names; if the schema declares only TECHNOLOGY, the lowercase value is invalid.

## 3. Using Enums Inside Input Objects

Enums are often combined with input objects to describe structured filters:

~~~graphql
enum BookGenre {
    TECHNOLOGY
    SCIENCE
    HISTORY
    FICTION
}

input BookFilterInput {
    keyword: String
    genre: BookGenre
    includeOutOfPrint: Boolean = false
}

type Query {
    books(filter: BookFilterInput): [Book!]!
}
~~~

Client sends:

~~~graphql
query SearchBooks($filter: BookFilterInput) {
    books(filter: $filter) {
        id
        title
        genre
    }
}
~~~

Variables:

~~~json
{
    "filter": {
        "keyword": "Spring",
        "genre": "TECHNOLOGY",
        "includeOutOfPrint": false
    }
}
~~~

GraphQL validates both the BookFilterInput structure and the value of the genre field. If genre does not belong to BookGenre, the request is rejected before the resolver receives the data.

Enums can also be used in lists:

~~~graphql
input BookSearchInput {
    genres: [BookGenre!]
}
~~~

Clients can pass multiple values:

~~~json
{
    "genres": ["TECHNOLOGY", "SCIENCE"]
}
~~~

`[BookGenre!]` allows the list to be null, while each element in the list cannot be null. If both the list and all elements must be non-null, use `[BookGenre!]!`.

## 4. Enums Can Be Used for Both Input and Output

An enum type is not just for input. The same enum can be used as an argument, an input object field, and the return type of an output field.

~~~graphql
enum OrderStatus {
    PENDING
    CONFIRMED
    SHIPPING
    COMPLETED
    CANCELLED
}

input OrderFilterInput {
    status: OrderStatus
}

type Order {
    id: ID!
    status: OrderStatus!
}

type Query {
    order(id: ID!): Order
    orders(filter: OrderFilterInput): [Order!]!
}
~~~

Clients can filter by status and receive the status of each order:

~~~graphql
query OrdersByStatus($filter: OrderFilterInput) {
    orders(filter: $filter) {
        id
        status
    }
}
~~~

Variables:

~~~json
{
    "filter": {
        "status": "SHIPPING"
    }
}
~~~

Response:

~~~json
{
    "data": {
        "orders": [
            {
                "id": "order-1001",
                "status": "SHIPPING"
            }
        ]
    }
}
~~~

When an enum appears in the response, GraphQL serializes the internal value into the enum value name published by the schema. Clients receive one of the defined enum names rather than an arbitrary status string.

## 5. Mapping Enum Inputs to Java in Spring for GraphQL

A simple and maintainable approach is to match Java enum constant names with the enum values in the SDL.

GraphQL SDL:

~~~graphql
enum BookGenre {
    TECHNOLOGY
    SCIENCE
    HISTORY
    FICTION
}

type Query {
    booksByGenre(genre: BookGenre!): [Book!]!
}
~~~

Java enum:

~~~java
package com.example.catalog.book;

public enum BookGenre {
    TECHNOLOGY,
    SCIENCE,
    HISTORY,
    FICTION
}
~~~

Resolver using `@Argument`:

~~~java
package com.example.catalog.graphql;

import com.example.catalog.book.Book;
import com.example.catalog.book.BookGenre;
import com.example.catalog.book.BookService;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

import java.util.List;

@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> booksByGenre(@Argument("genre") BookGenre genre) {
        return bookService.findByGenre(genre);
    }
}
~~~

Spring for GraphQL receives the argument already validated by GraphQL and binds it to the Java parameter. When enum value names in the schema match Java constant names, the mapping is straightforward.

The service accepts BookGenre instead of String:

~~~java
@Service
public class BookService {

    public List<Book> findByGenre(BookGenre genre) {
        return bookRepository.findByGenre(genre);
    }
}
~~~

This gives you compiler type checking. In business code, there is no need to compare strings like `"TECHNOLOGY"` or manually validate against a list of valid names.

If enum names in SDL differ from Java constant names or need to map to different internal values, you must configure enum value mapping or an appropriate conversion mechanism in the GraphQL runtime. Do not assume differing names will automatically convert correctly.

## 6. Binding Enums in Java Input Objects

When an enum is inside an input object, declare the Java property using the corresponding enum type.

SDL:

~~~graphql
enum BookGenre {
    TECHNOLOGY
    SCIENCE
    HISTORY
    FICTION
}

input BookFilterInput {
    keyword: String
    genre: BookGenre
}

type Query {
    books(filter: BookFilterInput): [Book!]!
}
~~~

Java DTO:

~~~java
package com.example.catalog.book;

public record BookFilterInput(
        String keyword,
        BookGenre genre
) {
}
~~~

Controller:

~~~java
@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books(@Argument("filter") BookFilterInput filter) {
        return bookService.search(filter);
    }
}
~~~

When the client passes:

~~~json
{
    "filter": {
        "keyword": "GraphQL",
        "genre": "TECHNOLOGY"
    }
}
~~~

the genre field binds to BookGenre.TECHNOLOGY in the Java object. If the client omits genre or passes null, the Java property can receive null because the field in SDL is nullable. The service should handle that according to filter semantics, such as applying no genre condition.

If the schema declares `genre: BookGenre!`, the client must supply a valid non-null enum value. The Java code should also uphold that guarantee in the application's processing rules.

## 7. Default Values and Null with Enums

An enum argument or input field can declare a default value. Default values in SDL use an unquoted enum literal:

~~~graphql
enum SortDirection {
    ASC
    DESC
}

input BookSortInput {
    direction: SortDirection = ASC
}

type Query {
    books(sort: BookSortInput): [Book!]!
}
~~~

When the client omits direction, GraphQL uses ASC. If the client passes direction as DESC, DESC is used.

~~~graphql
query SortedBooks($sort: BookSortInput) {
    books(sort: $sort) {
        id
        title
    }
}
~~~

If the sort variable does not include direction:

~~~json
{
    "sort": {}
}
~~~

direction receives the default ASC.

If direction is a nullable field and the client explicitly sends null:

~~~json
{
    "sort": {
        "direction": null
    }
}
~~~

the value remains null and does not automatically switch to ASC. The application must decide whether null means no sorting, falls back to a default order in the service, or is rejected by business rules.

If declared as `direction: SortDirection! = ASC`, the client can omit the field because it has a default; however, explicitly sending null is still invalid.

Do not confuse schema default values with fallbacks in Java. SDL defaults are applied while GraphQL processes input; service fallbacks are separate business rules and must be designed consistently.

## 8. How Does GraphQL Validate Enum Inputs?

Enums allow invalid input data to be caught early. Two situations are common.

**Enum literal does not exist in the schema:**

~~~graphql
query {
    booksByGenre(genre: FANTASY) {
        id
    }
}
~~~

If BookGenre does not declare FANTASY, the document fails the validation step. The resolver is never called.

**Variable contains an invalid enum value:**

Operation declaration:

~~~graphql
query BooksByGenre($genre: BookGenre!) {
    booksByGenre(genre: $genre) {
        id
    }
}
~~~

Variables:

~~~json
{
    "genre": "FANTASY"
}
~~~

GraphQL cannot coerce this value into BookGenre because FANTASY is not in the enum. The request is rejected before field execution.

You can distinguish the validation layers:

| Layer | Example | Result |
| --- | --- | --- |
| GraphQL schema/validation | Enum literal not present in schema | Request error, resolver has not run |
| Variable coercion | JSON variable contains invalid enum name | Request error, resolver has not run |
| Java binding | Incompatible Java type or enum mapping | May raise an error during argument binding |
| Business logic | Valid enum, but not allowed in current state | Resolver/service rejects the operation |

For example, the enum value CANCELLED is valid according to the schema, yet the user lacks permission to cancel the order or the order is already completed. That is business validation and authorization, not GraphQL enum validation.

## 9. Designing and Evolving Enums Safely

Enums are part of the public API contract. Changing the list of values can impact both server and clients.

**Choose stable, meaningful values.** Use names like PENDING, COMPLETED, or CANCELLED rather than names tied to internal implementation details. Enum values should reflect domain concepts that clients understand.

**Use a consistent naming convention.** Enum values typically use uppercase with underscores, such as IN_PROGRESS or OUT_OF_STOCK. GraphQL is case-sensitive, so standardize from the start.

**Do not use enums for open-ended data.** If the list of values changes frequently or is administrator-defined, a String or object type is a better fit. Enums fit when the set of options is schema-controlled and evolves with API versions.

**Adding enum values requires considering clients.** Adding a value is usually compatible with clients that only send older values. However, clients receiving enums in output may use exhaustive switches or schema-generated code; a new value can break older clients that do not handle it. Clients should include a fallback branch for unknown enum values.

**Do not delete or rename values arbitrarily.** Removing or renaming an enum value can invalidate existing requests and break client response handling. Mark values deprecated, announce a migration path, and remove them only under an appropriate versioning plan.

You can mark an obsolete enum value using the `@deprecated` directive:

~~~graphql
enum OrderStatus {
    PENDING
    PROCESSING
    SHIPPED
    DELIVERED
    OLD_COMPLETE @deprecated(reason: "Use DELIVERED instead")
}
~~~

The deprecated value remains in the schema for compatibility, while GraphQL tooling can warn clients to migrate to the new value.

## 10. Enums and Business Security

Enums restrict the set of values clients can send, but they do not replace authentication and authorization.

Example:

~~~graphql
enum UserRole {
    READER
    EDITOR
    ADMIN
}

input ChangeRoleInput {
    userId: ID!
    role: UserRole!
}
~~~

Just because the schema allows ADMIN does not mean every user is allowed to assign that role. The server must verify:

- Who is sending the request.
- Whether the sender has permission to change roles.
- Whether the target user falls within the sender's administrative scope.
- Whether the change complies with current security policies.

Do not rely on an enum passed by the client to determine the client's own permissions. Permissions must come from a trusted server-side security context and be enforced in the resolver/service or method security layer.

## 11. Testing Enum Inputs with GraphQlTester

You can use GraphQlTester to verify that enums passed through variables are bound into the resolver:

~~~java
@Test
void filtersBooksByGenre() {
    graphQlTester.document("""
            query BooksByGenre($genre: BookGenre!) {
                booksByGenre(genre: $genre) {
                    id
                    title
                }
            }
            """)
        .variable("genre", "TECHNOLOGY")
        .execute()
        .path("booksByGenre[0].title")
        .entity(String.class)
        .isEqualTo("Spring in Action");
}
~~~

With an input object:

~~~java
@Test
void filtersBooksWithInputObject() {
    graphQlTester.document("""
            query SearchBooks($filter: BookFilterInput) {
                books(filter: $filter) {
                    id
                    title
                }
            }
            """)
        .variable("filter", Map.of(
            "keyword", "Spring",
            "genre", "TECHNOLOGY"
        ))
        .execute()
        .path("books[0].title")
        .entity(String.class)
        .isEqualTo("Spring in Action");
}
~~~

Additional tests to include:

- Passing every valid enum value.
- Passing a non-existent enum value.
- Distinguishing unquoted enum literals from String literals.
- Omitting an enum field with a default and passing explicit null.
- Passing enums inside lists and nested input objects.
- Verifying the resolver receives the expected Java enum constant.
- Verifying a valid enum rejected by business rules or access control.
- Verifying clients handle new or deprecated output values.

Tests should verify both the GraphQL output and service behavior. For validation/coercion errors, verify that the response contains errors and confirm the resolver was not invoked.

## 12. Key Takeaways

- Enums declare a finite set of values using the enum keyword in SDL.
- Enum literals in a GraphQL document are unquoted; JSON variables represent enums as strings.
- Enums can be used in arguments, input object fields, lists, and output fields.
- GraphQL validates enum literals and variables before the resolver executes.
- Java enums can receive enum values when constant names match the schema enum values.
- Default values apply when a field is omitted; explicit null remains null if the field is nullable.
- Enums restrict choices but do not replace business validation or authorization.
- Adding, deprecating, renaming, or removing enum values requires assessing client impact.

Enum inputs help APIs clearly communicate valid options and catch mistyped data right at the GraphQL boundary. When combined with consistent SDL, matching Java enums, business checks, and GraphQlTester tests, a Spring for GraphQL application can handle input states and choices safely and maintainably.
