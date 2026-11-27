# Input object type

In GraphQL, an **input object type** is a data type used to group multiple input values into a structured object. Instead of declaring numerous separate arguments on a field, a schema can define an input type and use it as an argument for a Query or Mutation.

Input objects are especially useful for search, filtering, creation, and update operations. With Spring for GraphQL, this input object can be mapped to a Java class or record via the @Argument annotation, allowing controllers to receive structured data and forward it to the business layer.

## 1. What is an input object type?

An input object is declared using the input keyword in SDL:

~~~graphql
input BookFilter {
    keyword: String
    genre: String
    authorId: ID
}
~~~

BookFilter is an input object type consisting of three fields:

- keyword accepts a search string.
- genre accepts a book genre.
- authorId accepts an author identifier.

An input object is not a directly invocable operation by itself. It must be used in an input position, typically as a field argument:

~~~graphql
type Query {
    books(filter: BookFilter): [Book!]!
}
~~~

Clients pass an object conforming to the declared structure:

~~~graphql
query SearchBooks($filter: BookFilter) {
    books(filter: $filter) {
        id
        title
    }
}
~~~

Variables:

~~~json
{
    "filter": {
        "keyword": "Spring",
        "genre": "TECHNOLOGY",
        "authorId": "author-7"
    }
}
~~~

GraphQL validates the input structure and types against the schema before passing the data to the resolver. Clients cannot arbitrarily add fields outside the BookFilter definition or pass a value incompatible with the declared type.

## 2. Distinguishing input objects from output objects

GraphQL distinguishes between types used to receive data from clients and types used to return data to clients.

| Characteristic | Input object | Output object |
| --- | --- | --- |
| Declaration | input | type |
| Purpose | Receives input data | Describes returned data |
| Where used | Arguments, input fields, input-typed variables | Field return types and selection sets |
| Has field arguments | No | Can have them |
| Can contain output objects | No | Can contain objects, interfaces, or unions |

Example output type:

~~~graphql
type Book {
    id: ID!
    title: String!
    author: Author
}
~~~

Example input type:

~~~graphql
input CreateBookInput {
    title: String!
    authorId: ID!
}
~~~

These two kinds of types are not interchangeable. You cannot declare an argument of type Book if Book is an output object; nor can you use CreateBookInput as a field's return type for clients to select subfields from.

Keeping them separate lets the schema express the purpose of data clearly. Output types can contain computed fields, relationships, and resolvers. Input types only describe the values clients are permitted to send in.

## 3. Valid data types inside an input object

Fields of an input object may only use valid input types:

- Built-in scalars such as Int, Float, String, Boolean, ID.
- Enums.
- Other input objects.
- Lists of valid input types.
- Non-null variants created with an exclamation mark.

Example:

~~~graphql
enum BookGenre {
    TECHNOLOGY
    SCIENCE
    HISTORY
    FICTION
}

input AuthorFilter {
    authorId: ID
    nameContains: String
}

input BookFilter {
    keyword: String
    genre: BookGenre
    author: AuthorFilter
    years: [Int!]
    includeOutOfPrint: Boolean = false
}
~~~

In this example:

- genre only accepts one of the declared enum values.
- author is a nested input object.
- years is a list of integers where each element cannot be null.
- includeOutOfPrint has a default value of false.

Do not use output objects, interfaces, or unions as field types of an input object. Input objects also do not declare separate field resolvers or arguments on individual fields. If you need to model a structured set of input choices, use scalars, enums, or nested input objects.

### Nested input object example

Schema:

~~~graphql
input DateRangeInput {
    from: String
    to: String
}

input BookSearchInput {
    keyword: String
    author: AuthorFilter
    published: DateRangeInput
}

type Query {
    searchBooks(input: BookSearchInput): [Book!]!
}
~~~

Operation:

~~~graphql
query SearchBooks($input: BookSearchInput) {
    searchBooks(input: $input) {
        id
        title
    }
}
~~~

Variables:

~~~json
{
    "input": {
        "keyword": "GraphQL",
        "author": {
            "nameContains": "Nguyen"
        },
        "published": {
            "from": "2022-01-01",
            "to": "2025-12-31"
        }
    }
}
~~~

Nested structures allow grouping conditions by business meaning. If date-time filters are used in a real application, define a custom scalar matching your date-time format and time zone rules instead of using an unconstrained string.

## 4. Required fields, optional fields, and the exclamation mark

Within an input object, a field can be required or optional.

~~~graphql
input CreateBookInput {
    title: String!
    authorId: ID!
    subtitle: String
}
~~~

- title and authorId are required input fields because they have non-null types and no default value.
- subtitle is an optional input field because its type allows null.

Clients must provide the two required fields:

~~~json
{
    "title": "Spring for GraphQL",
    "authorId": "author-7"
}
~~~

If title is omitted or title: null is sent, the request is invalid at the input coercion step. The resolver does not receive invalid input to execute.

A non-null field with a default value does not require the client to pass it, because GraphQL can use the default value when the field is omitted:

~~~graphql
input BookPageInput {
    page: Int! = 1
    size: Int! = 20
}
~~~

In this case, the client can omit page or size; GraphQL uses the corresponding default. If the client explicitly passes null for a non-null field, the request is still invalid.

## 5. Distinguishing omitted fields from null fields

An important point when designing input is that **omitting a field** and **sending a field with null** are two distinct states.

Consider the input type:

~~~graphql
input UpdateBookInput {
    title: String
    subtitle: String
}
~~~

A client can send:

~~~json
{
    "title": "New title"
}
~~~

Here subtitle is omitted. Or the client can send:

~~~json
{
    "title": "New title",
    "subtitle": null
}
~~~

Here subtitle is explicitly sent with the value null.

GraphQL preserves this distinction during input object coercion: an omitted field may be absent from the coerced value map, while a field sent as null has a null value. This difference is crucial for update operations:

- Omitting subtitle may mean keeping the current subtitle unchanged.
- Sending subtitle: null may mean clearing the subtitle.

If you map directly to a Java DTO where both cases turn into Java null, the application can lose the information of whether the client sent the field. For update APIs that need to distinguish these two states, use a data type or binding mechanism capable of tracking field presence, or design the input explicitly with an action flag such as clearSubtitle. Test both the omitted and explicit-null cases.

### Default values and null

A default value is applied when a field is not provided. It does not mean every null value is automatically replaced with the default.

~~~graphql
input SearchInput {
    keyword: String = "GraphQL"
}
~~~

- Input {} uses the default value GraphQL.
- Input {"keyword": "Spring"} uses the value Spring.
- Input {"keyword": null} retains null because the field allows null.

Understanding these three states prevents unintended data overwrites or unwanted filters.

## 6. Using input objects for Queries and Mutations

Input objects can be used as Query arguments to describe search criteria:

~~~graphql
input BookFilterInput {
    keyword: String
    genre: BookGenre
    authorId: ID
}

type Query {
    books(filter: BookFilterInput): [Book!]!
}
~~~

For write operations, input objects typically bundle the attributes a client sends to create or update data:

~~~graphql
input CreateBookInput {
    title: String!
    description: String
    authorId: ID!
    genre: BookGenre!
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
}
~~~

Operation:

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
    createBook(input: $input) {
        id
        title
        genre
    }
}
~~~

Variables:

~~~json
{
    "input": {
        "title": "Learning Spring GraphQL",
        "description": "A practical introduction",
        "authorId": "author-7",
        "genre": "TECHNOLOGY"
    }
}
~~~

Input objects establish a named, reusable input contract. When multiple mutations share the same data structure, they can share an input type if the semantics and validation rules are genuinely identical. If two operations have different business requirements, create separate input types to prevent one change from unexpectedly affecting another API.

## 7. Mapping input objects to Java with Spring for GraphQL

Spring for GraphQL can convert an input object into a Java class or record. Example SDL:

~~~graphql
input CreateBookInput {
    title: String!
    description: String
    authorId: ID!
    genre: BookGenre!
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
}
~~~

Corresponding Java enum declaration:

~~~java
public enum BookGenre {
    TECHNOLOGY,
    SCIENCE,
    HISTORY,
    FICTION
}
~~~

Java record declaration:

~~~java
public record CreateBookInput(
        String title,
        String description,
        String authorId,
        BookGenre genre
) {
}
~~~

Controller:

~~~java
package com.example.catalog.graphql;

import com.example.catalog.book.Book;
import com.example.catalog.book.BookService;
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
    public Book createBook(@Argument("input") CreateBookInput input) {
        return bookService.create(input);
    }
}
~~~

Spring for GraphQL performs the main steps:

1. Reads the input argument from the operation.
2. GraphQL validates the object against CreateBookInput in the schema.
3. Spring converts the coerced value to the target Java type.
4. The method mapped with @MutationMapping receives the object and calls the service.
5. The returned result is completed by the GraphQL engine according to the client's selection set.

Java property names must be compatible with the field names in the input object. If complex mapping is required, you can use a class with constructors or an appropriate conversion mechanism rather than forcing every input to be a record.

### Nested input objects in Java

Given SDL:

~~~graphql
input DateRangeInput {
    from: String
    to: String
}

input BookSearchInput {
    keyword: String
    published: DateRangeInput
}

type Query {
    searchBooks(input: BookSearchInput): [Book!]!
}
~~~

Corresponding Java records:

~~~java
public record DateRangeInput(String from, String to) {
}

public record BookSearchInput(
        String keyword,
        DateRangeInput published
) {
}
~~~

Resolver:

~~~java
@QueryMapping
public List<Book> searchBooks(@Argument("input") BookSearchInput input) {
    return bookService.search(input);
}
~~~

The Java types must mirror the nested structure of the SDL. If the schema changes field names or data types, update the corresponding DTOs and test the binding.

## 8. Validation for input objects

GraphQL performs schema-level checks before calling the resolver:

- Whether the field exists in the input type.
- Whether the value is compatible with the scalar or enum.
- Whether nested input objects match the structure.
- Whether non-null fields are missing or receive null.
- Whether lists contain elements of the right type.

These checks do not replace business validation. For example, limit: Int! can still receive a negative number; GraphQL only confirms it is a non-null integer. Rules such as maximum page size, title length, author ownership, or allowed update states must be validated in the application.

Example validation in a service:

~~~java
@Service
public class BookService {

    public Book create(CreateBookInput input) {
        if (input.title() == null || input.title().isBlank()) {
            throw new IllegalArgumentException("Title must not be blank");
        }

        if (input.title().length() > 200) {
            throw new IllegalArgumentException("Title is too long");
        }

        if (!authorExists(input.authorId())) {
            throw new IllegalArgumentException("Author does not exist");
        }

        return saveBook(input);
    }
}
~~~

In real projects, you can use Jakarta Bean Validation with constraints such as @NotBlank, @Size, @Min, and @Max, combined with appropriate validation configuration for Spring GraphQL. Whichever approach you use, validation errors must be translated into GraphQL errors with appropriate messages and error codes; avoid returning internal details or sensitive data in messages.

Example input type with limits alongside SDL:

~~~graphql
input BookPageInput {
    page: Int! = 1
    size: Int! = 20
}
~~~

The resolver or service must still ensure that page is greater than or equal to 1 and size does not exceed system limits. The schema declares types and requiredness; the service enforces domain rules.

## 9. Designing extensible input objects

A good input object should reflect a cohesive group of data with business meaning.

**Name by purpose.** Names such as CreateBookInput, UpdateBookInput, and BookFilterInput make clear what the data is used for. Avoid generic names like InputData or CommonInput.

**Do not cram everything into one giant input type.** If create, update, and search have different requirements, splitting types helps control required fields, defaults, and modification permissions.

**Use nested input objects for independent data groups.** For example, DateRangeInput or AuthorFilterInput can be reused where the semantics match.

**Limit size and depth.** Large input lists or deeply nested objects can increase parsing, validation, and processing costs. Enforce appropriate limits at the schema, transport, or business layer.

**Do not use input as a substitute for authorization.** A client sending authorId or ownerId does not mean they are permitted to act on that resource. The server must verify identity and permissions on each resource.

**Be careful with update semantics.** Define clearly what an omitted field, a null field, and a field with a new value mean. If the API needs to clear a value, specify that convention clearly in the input and test it.

## 10. Common mistakes

| Symptom | Common cause | How to resolve |
| --- | --- | --- |
| Schema reports input field uses wrong type | Output object, interface, or union used in an input definition. | Switch to an appropriate scalar, enum, or input object. |
| Missing required field | Non-null input field with no default was omitted. | Provide the field with a non-null value. |
| Invalid enum | Client sent a value not in the enum. | Check enum value names against the SDL. |
| Nested input object fails to bind | JSON structure or Java type is incompatible with SDL. | Verify field names, nested DTOs, and data types. |
| Resolver receives null | Optional field was omitted or explicitly sent as null. | Check operation variables and default value rules. |
| Cannot distinguish omitted from null on update | A plain DTO may represent both states as Java null. | Use presence-preserving binding or design explicit indicators in the input. |
| Schema-valid value violates business rules | Schema only checks types, not all domain rules. | Validate in the service and return an appropriate GraphQL error. |
| Client sends object with unknown field | JSON does not match the declared input type. | Fix the field name or update the schema in a controlled manner. |

When debugging, check the SDL, request variables, Java argument types, and service validation in order. If an error occurs before the resolver runs, check input coercion or the schema. If the resolver ran but business logic rejected the data, check validation and application exception handling.

## 11. Testing input objects with GraphQlTester

You can use GraphQlTester to verify mutations that accept an input object and return expected data:

~~~java
@Test
void createsBookFromInput() {
    graphQlTester.document("""
            mutation CreateBook($input: CreateBookInput!) {
                createBook(input: $input) {
                    id
                    title
                }
            }
            """)
        .variable("input", Map.of(
            "title", "Learning Spring GraphQL",
            "authorId", "author-7",
            "genre", "TECHNOLOGY"
        ))
        .execute()
        .path("createBook.title")
        .entity(String.class)
        .isEqualTo("Learning Spring GraphQL");
}
~~~

In addition to valid cases, test:

- Missing required fields.
- Sending null for a non-null field.
- Sending a nonexistent enum value.
- Sending a malformed nested input object.
- Omitting a field with a default versus explicitly sending null.
- Sending type-valid input that violates business rules.
- Updates with an omitted field versus a field sent as null.

GraphQL-level tests verify the schema and binding. Service tests verify business rules. Integration tests verify that errors are translated into GraphQL responses properly.

## 12. Key points to remember

- Input object types are declared with the input keyword and are only used in input positions.
- Fields of an input object can only contain scalars, enums, other input objects, lists, and their non-null variants.
- Output objects declared with type cannot be used as input types.
- Non-null fields without defaults are required; defaults are used when a field is omitted.
- Omitting a field and sending a field as null are two distinct states, especially important for update operations.
- Spring for GraphQL can bind input objects to Java classes or records via @Argument.
- GraphQL validates structure and types; the service must still enforce business rules, authorization, and resource limits.

Input objects allow a GraphQL API to accept structured data cleanly, with extensibility and an explicit contract. When paired with a strict schema, appropriate Java DTOs, and business-layer validation, a Spring for GraphQL application can safely handle complex filters as well as create and update operations.
