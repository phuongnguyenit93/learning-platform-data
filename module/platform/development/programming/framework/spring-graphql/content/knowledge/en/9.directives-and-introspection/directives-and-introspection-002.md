# Built-in @skip

In GraphQL, a directive is an instruction attached to an operation or schema element to alter how GraphQL processes part of a request. A commonly used built-in directive on the client side is **@skip**. This directive lets a client instruct GraphQL to skip a field or a selection branch when a Boolean condition evaluates to true.

In Spring for GraphQL, @skip is handled by the GraphQL engine during operation execution. The application does not need a dedicated controller method to implement this directive. However, understanding its exact condition, valid locations, and impact on resolvers helps build flexible requests, write accurate tests, and avoid confusing response-control directives with security mechanisms.

## 1. What Is @skip?

`@skip` is a built-in GraphQL directive used to exclude a selection from execution results when its condition is `true`.

Syntax:

~~~graphql
fieldName @skip(if: Boolean!)
~~~

The `if` argument has type `Boolean!`, meaning it must receive a non-null Boolean value. When `if` is `true`, the selection is marked to be skipped. When `if` is `false`, the selection is executed normally.

Example schema:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    description: String
    author: Author
}
~~~

A client can request that the description field be skipped:

~~~graphql
query BookDetail($skipDescription: Boolean!) {
    book(id: "book-42") {
        id
        title
        description @skip(if: $skipDescription)
    }
}
~~~

If variables are:

~~~json
{
    "skipDescription": true
}
~~~

GraphQL does not execute the `description` selection and the field does not appear in the response:

~~~json
{
    "data": {
        "book": {
            "id": "book-42",
            "title": "Spring in Action"
        }
    }
}
~~~

If `skipDescription` is `false`, GraphQL executes the field and the response includes description if the resolver returns data.

## 2. Why Use @skip?

A screen may display different data depending on tabs, state, or user choices. If the client always sends all fields, the server may have to run resolvers that are unnecessary for the current UI view.

For example, a book detail screen has a summary view and a full view. Both need the same basic information, but only the full view needs description:

~~~graphql
query BookScreen($fullView: Boolean!) {
    book(id: "book-42") {
        id
        title
        description @skip(if: $fullView == false)
    }
}
~~~

A direct comparison expression inside a GraphQL argument like the one above is invalid. GraphQL does not support arbitrary Boolean expressions inside arguments. Compute the condition on the client and pass it via a variable:

~~~graphql
query BookScreen($skipDescription: Boolean!) {
    book(id: "book-42") {
        id
        title
        description @skip(if: $skipDescription)
    }
}
~~~

On the client side:

- Full view: pass `skipDescription = false`.
- Summary view: pass `skipDescription = true`.

`@skip` keeps the operation document stable, while variables determine which fields are included in the result on each call.

## 3. The `if` Condition and Variables

The `if` argument must have a non-null Boolean type. The common approach is declaring an operation variable of type `Boolean!`:

~~~graphql
query ProductDetail($hideStock: Boolean!) {
    product(id: "product-10") {
        id
        name
        stockQuantity @skip(if: $hideStock)
    }
}
~~~

When passing:

~~~json
{
    "hideStock": true
}
~~~

the stockQuantity field is skipped.

When passing:

~~~json
{
    "hideStock": false
}
~~~

the stockQuantity field is executed.

If the variable is missing or null, the request fails the non-null type constraint and is rejected during variable processing. You can declare a default value for the variable to avoid having to pass it in every case:

~~~graphql
query ProductDetail($hideStock: Boolean! = false) {
    product(id: "product-10") {
        id
        name
        stockQuantity @skip(if: $hideStock)
    }
}
~~~

If the client does not supply `hideStock`, GraphQL uses the default false and the stockQuantity field is selected.

Do not use the string `"true"` or the number `1` instead of a Boolean. The value must be a JSON Boolean:

~~~json
{
    "hideStock": true
}
~~~

## 4. Where Can @skip Be Applied?

According to the GraphQL specification, `@skip` can be placed at three locations in an executable document:

| Location | Meaning |
| --- | --- |
| `FIELD` | Skips a specific field. |
| `FRAGMENT_SPREAD` | Skips a fragment usage. |
| `INLINE_FRAGMENT` | Skips an inline fragment. |

### Skipping a Field

~~~graphql
query BookDetail($skipAuthor: Boolean!) {
    book(id: "book-42") {
        id
        title
        author @skip(if: $skipAuthor) {
            id
            name
        }
    }
}
~~~

When `skipAuthor` is true, both the author field and its child selection set are skipped.

### Skipping a Fragment Spread

~~~graphql
fragment AuthorDetails on Author {
    id
    name
    biography
}

query BookDetail($skipAuthor: Boolean!) {
    book(id: "book-42") {
        id
        title
        author {
            ...AuthorDetails @skip(if: $skipAuthor)
        }
    }
}
~~~

When the condition is true, that usage of the AuthorDetails fragment is skipped. Other fields in author's selection set can still be executed if selected separately.

### Skipping an Inline Fragment

~~~graphql
query Search($skipBookDetails: Boolean!) {
    search(keyword: "Spring") {
        __typename
        ... on Book @skip(if: $skipBookDetails) {
            title
            isbn
        }
        ... on Author {
            name
        }
    }
}
~~~

When `skipBookDetails` is true, the inline fragment branch on Book is skipped. The Author branch is unaffected by that directive.

`@skip` cannot be placed arbitrarily everywhere. For example, this directive does not have locations for operation definitions, variable definitions, or fragment definitions. If you want to make a group of fields conditional, place the directive on the appropriate fragment spread or inline fragment.

## 5. Combining @skip with Nested Fields

The directive can be placed on fields at any level in the selection set, as long as the location is valid.

~~~graphql
query BookDetails(
    $skipDescription: Boolean!
    $skipAuthor: Boolean!
    $skipReviews: Boolean!
) {
    book(id: "book-42") {
        id
        title
        description @skip(if: $skipDescription)
        author @skip(if: $skipAuthor) {
            id
            name
        }
        reviews @skip(if: $skipReviews) {
            id
            rating
            comment
        }
    }
}
~~~

The client can control each branch independently:

~~~json
{
    "skipDescription": false,
    "skipAuthor": true,
    "skipReviews": true
}
~~~

The response includes description, but excludes author and reviews:

~~~json
{
    "data": {
        "book": {
            "id": "book-42",
            "title": "Spring in Action",
            "description": "A practical guide"
        }
    }
}
~~~

Each directive is evaluated using the variable values of the current request. A condition on one field does not automatically affect sibling fields or other fields in the operation.

## 6. @skip vs. @include

GraphQL provides two conditional directives with complementary semantics:

- `@skip(if: true)` omits the selection.
- `@include(if: true)` includes the selection in execution.

Example using `@include`:

~~~graphql
query BookDetail($showAuthor: Boolean!) {
    book(id: "book-42") {
        id
        title
        author @include(if: $showAuthor) {
            id
            name
        }
    }
}
~~~

If `showAuthor` is true, author is executed. If false, author is excluded from the result.

The same logic can be expressed with `@skip`:

~~~graphql
query BookDetail($hideAuthor: Boolean!) {
    book(id: "book-42") {
        id
        title
        author @skip(if: $hideAuthor) {
            id
            name
        }
    }
}
~~~

When both directives are used on the same selection:

~~~graphql
query BookDetail(
    $skipAuthor: Boolean!
    $includeAuthor: Boolean!
) {
    book(id: "book-42") {
        id
        title
        author
            @skip(if: $skipAuthor)
            @include(if: $includeAuthor) {
                id
                name
            }
    }
}
~~~

The selection is executed only when the skip condition is false and the include condition is true.

| `skip(if)` | `include(if)` | Result |
| --- | --- | --- |
| false | true | Execute selection |
| true | true | Skip selection |
| false | false | Skip selection |
| true | false | Skip selection |

In practice, one directive is usually enough to express intent clearly. Use both together only when there is a clear reason and ensure the conditions do not confuse readers of the operation.

## 7. How Does GraphQL Process @skip?

`@skip` is an executable directive. The GraphQL engine validates the document, evaluates the condition, and removes the selection from the set of fields to execute when the condition is true.

High-level flow:

~~~mermaid
flowchart TD
    A["Client sends operation and variables"] --> B["Parse and validate document"]
    B --> C["Coerce variables"]
    C --> D["Evaluate @skip(if)"]
    D --> E{"if = true?"}
    E -->|Yes| F["Skip selection"]
    E -->|No| G["Execute field resolver"]
    F --> H["Build response from remaining fields"]
    G --> H
~~~

Several key points to understand:

- The schema must still contain the selected field. `@skip` does not make a nonexistent field valid.
- The document must still be valid in syntax, field names, arguments, types, and selection sets.
- Variables are still validated and coerced according to their declarations, even when a field may be skipped.
- When a selection is skipped, that field's data fetcher/resolver is not invoked.
- A skipped field is not returned as a key with a null value; the key is omitted from the result object.
- Other unskipped fields still execute normally.

If all child fields in an object selection are skipped, the resulting object may omit those keys. Clients should handle missing keys according to the request conditions sent, rather than assuming a missing key means the field's value is null.

## 8. @skip in Spring for GraphQL

Spring for GraphQL uses GraphQL Java to execute operations. Built-in directives such as `@skip` are supported out of the box by the engine, so there is no need to create Java annotations, `@SchemaMapping` methods, or a `RuntimeWiringConfigurer` just to enable this feature.

Example schema:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    reviews: [Review!]!
}

type Review {
    id: ID!
    rating: Int!
}
~~~

Controller with a resolver for reviews:

~~~java
@Controller
public class BookReviewController {

    private final ReviewService reviewService;

    public BookReviewController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @SchemaMapping(typeName = "Book", field = "reviews")
    public List<Review> reviews(Book book) {
        return reviewService.findByBookId(book.id());
    }
}
~~~

Operation:

~~~graphql
query BookDetail($skipReviews: Boolean!) {
    book(id: "book-42") {
        id
        title
        reviews @skip(if: $skipReviews) {
            id
            rating
        }
    }
}
~~~

When `skipReviews` is true, the GraphQL engine skips the reviews field and the `reviews` method is not called. When `skipReviews` is false, the field is executed and Spring calls the mapping method to fetch the list of Reviews.

This can avoid unnecessary data queries in specific requests. However, if the root resolver has already preloaded reviews and attached them to the Book object, the directive cannot undo work that already happened in the root resolver. Place data loading in the appropriate resolver or use a query strategy that accounts for the selection set.

## 9. Testing @skip with GraphQlTester

You should test both branches of the condition: skip and execute.

Example when skipping the reviews field:

~~~java
@Test
void skipsReviewsWhenVariableIsTrue() {
    graphQlTester.document("""
            query BookDetail($skipReviews: Boolean!) {
                book(id: "book-42") {
                    id
                    title
                    reviews @skip(if: $skipReviews) {
                        id
                        rating
                    }
                }
            }
            """)
        .variable("skipReviews", true)
        .execute()
        .path("book.id")
        .entity(String.class)
        .isEqualTo("book-42");
}
~~~

You can verify that the reviews field does not appear in the response by inspecting the JSON response or using the path assertion API appropriate for your project's version of GraphQlTester.

Testing when not skipping:

~~~java
@Test
void executesReviewsWhenVariableIsFalse() {
    graphQlTester.document("""
            query BookDetail($skipReviews: Boolean!) {
                book(id: "book-42") {
                    reviews @skip(if: $skipReviews) {
                        id
                        rating
                    }
                }
            }
            """)
        .variable("skipReviews", false)
        .execute()
        .path("book.reviews[0].rating")
        .entity(Integer.class)
        .isEqualTo(5);
}
~~~

Beyond the response, you can use mocks or spies to verify that the reviews resolver is not called when the field is skipped and is called when the condition is false. Additional test cases to include:

- The skip variable is missing or receives null when declared non-null.
- An object field is skipped along with its entire child selection set.
- Fragment spreads and inline fragments with the directive.
- Combining @skip with @include.
- Nested fields with arguments and expensive resolvers.
- A non-null field being skipped: the key is omitted and no null propagation is triggered just because that field was skipped.

## 10. Inspecting Directives via Introspection

GraphQL supports introspection so clients or tools can discover the schema. You can query the list of directives, valid locations, and arguments published by the schema:

~~~graphql
query DirectiveDefinitions {
    __schema {
        directives {
            name
            locations
            args {
                name
                type {
                    kind
                    name
                    ofType {
                        kind
                        name
                    }
                }
            }
        }
    }
}
~~~

In the result, look for the directive named `skip` to inspect the `if` argument, its non-null Boolean type, and the supported locations. Tools and server versions may determine how built-in directives are exposed in the introspection list; if it is not shown, check the GraphQL specification and the endpoint's introspection capabilities.

Introspection helps discover the schema contract, but it does not replace testing specific operations. For `@skip` errors, check the document, variable types, variable values, and field locations.

## 11. @skip Is Not a Security Mechanism

`@skip` controls whether a field is included in the response of an operation. It does not grant or revoke data access permissions.

A client can send another request without attaching `@skip` to the field. Therefore, never rely on the UI hiding a field or the client passing skip=true to protect sensitive data.

For example, if the salary field is only for managers:

~~~graphql
type Employee {
    id: ID!
    name: String!
    salary: Float
}
~~~

Directive:

~~~graphql
query EmployeeDetail($skipSalary: Boolean!) {
    employee(id: "employee-7") {
        id
        name
        salary @skip(if: $skipSalary)
    }
}
~~~

If the client passes false, the salary field will be requested. The server must still verify whether the user is authorized to view salary using Spring Security, method security, resolver authorization, or another appropriate policy.

Use `@skip` to reduce unnecessary fields in the response; use server-side authorization to protect data. These two goals are independent of each other.

## 12. Common Pitfalls

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| `if` argument is rejected | Passing a String, number, or null instead of a non-null Boolean. | Declare a `Boolean!` variable and pass a JSON Boolean. |
| Field still appears | The skip condition is currently false. | Check the variable value and default value. |
| Field does not appear when expected | The skip variable is true or an include directive is false. | Check both @skip and @include on the selection. |
| Resolver does not run | The field was skipped or is not in the actual selection set. | Check the directives and the sent operation. |
| Field is invalid despite @skip | The field does not exist, has the wrong type, or the selection set is invalid. | Fix the document to match the schema; the directive does not bypass validation. |
| Sensitive data is still accessible | Using @skip as a field-hiding mechanism. | Add server-side authorization. |
| Query still takes a long time | The root resolver loads data before the nested field is skipped. | Move data loading into a field resolver or optimize the query strategy. |

## 13. Key Takeaways

- `@skip(if: Boolean!)` skips a selection when the condition is true.
- The directive can be applied to fields, fragment spreads, and inline fragments.
- Use Boolean variables to control fields per request; do not write arbitrary expressions in arguments.
- Skipped fields do not appear in the response and their resolvers are not invoked.
- The document and variables must still be valid; `@skip` does not bypass validation or coercion.
- `@include` has complementary logic; when both are used, a selection runs only if it is not skipped and is included.
- Spring for GraphQL handles built-in directives through the GraphQL engine without needing custom resolvers.
- `@skip` does not replace authorization and is not a data protection mechanism.

`@skip` is a straightforward way to control selection sets according to client needs. When used properly with variables, with a clear understanding of resolver impact and thorough testing, a Spring for GraphQL application can avoid executing unnecessary fields while keeping schema and security logic clear.
