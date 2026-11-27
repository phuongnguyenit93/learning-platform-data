# Schema Definition Language (SDL) in GraphQL

GraphQL Schema Definition Language (SDL) is a declarative language used to describe the contract of a GraphQL API. SDL specifies what data types the API has, what fields each type exposes, what arguments each field accepts, what return types are produced, and what operations clients are allowed to perform. The schema serves as the basis for GraphQL to validate queries before execution and produce a consistent response structure.

In Spring for GraphQL, schemas are typically written as `.graphqls` or `.gqls` files in the application's resources. Spring for GraphQL combines these definitions into a GraphQL Java schema; resolvers declared with `@QueryMapping`, `@SchemaMapping`, and related annotations provide data for the corresponding fields.

After this lesson, you will be able to:

- Read and write SDL syntax for schemas, types, fields, arguments, and directives.
- Distinguish between scalars, objects, enums, input objects, interfaces, and unions.
- Understand the meaning of lists and nullability in GraphQL data types.
- Design root operation types and organize schemas across multiple files.
- Use descriptions, custom scalars, directives, and type extensions appropriately.
- Evaluate the impact of schema changes on clients and Spring resolvers.

## 1. SDL describes the GraphQL contract

REST APIs are typically described by endpoints and request/response structures. GraphQL centers on a strongly typed schema. A client sends an operation selecting the fields it wants to read; the schema determines whether those fields exist, whether the arguments are valid, and what data types are returned.

For example, a library API might declare:

```graphql
type Query {
    book(id: ID!): Book
    books(limit: Int = 20): [Book!]!
}

type Book {
    id: ID!
    title: String!
    publishedYear: Int
}
```

The schema above defines two read fields on the root `Query` type. `book` takes a required `id` and returns a nullable `Book`. `books` takes an optional `limit`, defaulting to 20, and returns a non-null list of non-null `Book` elements.

SDL does not contain database query logic or business rules. It describes the shape and constraints of the API; resolvers perform the actual data fetching or transformation. Therefore, a schema can be validated and documented even before the resolvers are fully implemented.

## 2. Basic structure of a schema

A GraphQL schema consists of type definitions and has one or more root operation types. The three standard operation types are:

- `Query`: reads data.
- `Mutation`: modifies data.
- `Subscription`: receives an event stream.

Example of a complete schema:

```graphql
schema {
    query: Query
    mutation: Mutation
    subscription: Subscription
}

type Query {
    book(id: ID!): Book
    books: [Book!]!
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
}

type Subscription {
    bookCreated: Book!
}
```

`schema` explicitly specifies which object type serves as the root for each operation. If you use the default names `Query`, `Mutation`, and `Subscription`, the `schema` definition can be omitted; GraphQL automatically recognizes the root types by those names. If you use a different name, such as `RootQuery`, you must declare `schema { query: RootQuery }` to specify the root query type. The root query type is required; mutation and subscription are optional.

Type and field names are case-sensitive. By common convention, object type, interface, enum, input, and scalar names use PascalCase; fields, arguments, and enum values use camelCase or UPPER_SNAKE_CASE depending on project convention. Most importantly, choose one consistent convention.

## 3. Declaring fields and arguments

An object type contains fields that clients can select. Each field has a name, may have a list of arguments, and must have a return type:

```graphql
type Query {
    book(id: ID!): Book
    searchBooks(text: String!, limit: Int = 10): [Book!]!
}
```

In the example:

- `book` is the field name.
- `id` is an argument of type `ID!`, so the client must provide a value.
- `Book` is the return type; because there is no `!`, the field may return `null`.
- `searchBooks` accepts a required `text` and an optional `limit` with a default value of 10.
- `[Book!]!` indicates that the field always returns a list and each element in the list must also be non-null.

Arguments can be scalars, enums, or input objects. You cannot use a regular output object type as an argument type. When an operation needs multiple structured input values, group them into an input object rather than creating too many separate arguments.

```graphql
input BookFilter {
    authorId: ID
    publishedAfter: Int
    tags: [String!]
}

type Query {
    books(filter: BookFilter, limit: Int = 20): [Book!]!
}
```

Default values are written directly in SDL. Strings are enclosed in double quotes, numbers are written as literals, enum values are not quoted, and lists/objects use their corresponding syntax. A default value is only used when the client omits that argument or input field; it does not replace an explicit `null` value passed by the client.

## 4. Scalar types

A scalar is a primitive data type without subfields. GraphQL defines five built-in base scalars:

| Scalar | Meaning |
| --- | --- |
| `Int` | Signed 32-bit integer |
| `Float` | Double-precision floating-point number |
| `String` | Character string |
| `Boolean` | `true` or `false` value |
| `ID` | Identifier, serialized as a string; typically used for object identification keys |

Example:

```graphql
type Book {
    id: ID!
    title: String!
    pageCount: Int
    rating: Float
    available: Boolean!
}
```

Do not use `Int` for every numeric value. If data may exceed the 32-bit integer range, consider an appropriate custom scalar or represent it as a string per the API contract. `ID` represents an identifier, not a guarantee that the value is an integer.

### Custom scalars

When an API needs types such as dates/times, currency, or high-precision decimals, you can declare custom scalars:

```graphql
scalar DateTime
scalar Decimal

type AuditEvent {
    occurredAt: DateTime!
    amount: Decimal
}
```

SDL only names the scalar and registers it in the type system. The application still must define how to parse input values, validate, serialize output values, and map it to a Java type. With GraphQL Java, this is typically implemented via `GraphQLScalarType`/`Coercing` and registered through `RuntimeWiringConfigurer`; projects can also use scalars provided by extension libraries.

If a scalar follows a well-defined format specification, the `@specifiedBy` directive can attach a URL describing the serialization contract:

```graphql
scalar DateTime @specifiedBy(url: "https://example.org/specs/date-time")
```

The URL in the example should be replaced with the actual specification document the API commits to following. Clearly define timezone, precision, input format, and null representation so clients do not have to guess.

## 5. Object types and relationships between types

Object types are the core building blocks of a schema. They describe an object whose fields clients can query:

```graphql
type Author {
    id: ID!
    name: String!
}

type Book {
    id: ID!
    title: String!
    author: Author
}
```

The `Book.author` field references the `Author` object type, creating a nested relationship. Clients can select subfields as needed:

```graphql
query {
    book(id: "book-42") {
        title
        author {
            name
        }
    }
}
```

The schema lets you describe deeper relationships, but it does not dictate whether those relationships are loaded via joins, separate queries, caching, or DataLoader. Those choices belong to the execution layer. When designing many relational fields, account for the N+1 problem and server-side query depth/complexity limits.

## 6. Lists and nullability

GraphQL uses square brackets to declare a list and `!` to mark a type as non-null. Combining the two symbols produces four important forms:

| Type | Can field be null? | Can list be null? | Can elements be null? |
| --- | --- | --- | --- |
| `[Book]` | Yes | Yes | Yes |
| `[Book!]` | Yes | Yes | No |
| `[Book]!` | No | No | Yes |
| `[Book!]!` | No | No | No |

Example:

```graphql
type Query {
    optionalBooks: [Book]
    booksWithRequiredItems: [Book!]!
}
```

`[Book!]!` requires the resolver to return a non-null list containing no null elements. If the resolver finds no data, it must return an empty list instead of `null`. If a required element is null or fails during resolution, GraphQL applies null propagation: the null value bubbles up to the nearest nullable parent field, and the response may contain errors.

Choose nullability according to the business contract:

- Use non-null when the application can guarantee the field always has a valid value.
- Use nullable when missing data is a normal outcome, such as looking up a book by a nonexistent ID.
- Do not mark every field non-null just to make the response look strict; execution errors can cause null propagation wider than intended.
- For lists, decide separately whether the list itself can be null and whether individual elements can be null.

Changing nullability is a contract change. Changing an output from nullable to non-null can cause response errors if legacy data or a resolver still returns null. Changing an input from nullable to non-null can prevent older clients from sending valid requests.

## 7. Enum types

Enums restrict a field to a set of values published by the schema:

```graphql
enum BookStatus {
    DRAFT
    PUBLISHED
    ARCHIVED
}

type Book {
    id: ID!
    status: BookStatus!
}
```

Clients can only send a valid enum value in an operation. Enums make the schema more self-descriptive than free-form strings and enable code generation tools to create enum types on the client side.

When adding a new enum value, some clients with exhaustive switch statements or assumptions that only the old value set exists may need updates. Therefore, adding an enum value is generally less risky than removing or renaming one, but you still need to consider how clients handle unknown values.

## 8. Input objects and output objects

Input objects are used for data sent by the client. Object types are used for data returned by the server. The two serve different purposes and cannot be used interchangeably at will.

```graphql
input CreateBookInput {
    title: String!
    authorId: ID!
    publishedYear: Int
}

type Book {
    id: ID!
    title: String!
    publishedYear: Int
    author: Author
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
}
```

Input objects contain only input fields; each field has a scalar, enum, or input object type, optionally wrapped in list/non-null modifiers. Input fields have no arguments and cannot directly reference object types, interfaces, or unions. Conversely, output fields can return objects and accept arguments.

In Java, input objects can be bound to records or DTOs:

```java
public record CreateBookInput(
        String title,
        String authorId,
        Integer publishedYear) {}

@MutationMapping
public Book createBook(@Argument("input") CreateBookInput input) {
    return bookService.create(input);
}
```

SDL defines structure and nullability; business validation such as non-blank titles, author existence, or valid publication year ranges must be enforced at the application layer. You can combine this with Bean Validation in DTOs/services if the project has configured support for it.

## 9. Interfaces and unions

An interface describes a shared set of fields that multiple object types must implement. It is useful when different objects share part of their structure:

```graphql
interface Node {
    id: ID!
}

type Book implements Node {
    id: ID!
    title: String!
}

type Author implements Node {
    id: ID!
    name: String!
}

type Query {
    node(id: ID!): Node
}
```

An object implementing an interface must provide the required fields with compatible types. Clients can query common fields directly on the interface; to request fields specific to each concrete object, use inline fragments:

```graphql
query {
    node(id: "42") {
        id
        ... on Book {
            title
        }
        ... on Author {
            name
        }
    }
}
```

A union represents a result that can be one of several object types without requiring them to share any common fields:

```graphql
union SearchResult = Book | Author

type Query {
    search(text: String!): [SearchResult!]!
}
```

A union can only contain object types. Clients must use inline fragments to select specific fields of each member type; arbitrary fields cannot be queried directly on a union other than the `__typename` meta-field.

Choose an interface when the types share a genuine field contract. Choose a union when the types simply need to appear in the same result position without significant shared structure.

## 10. Directives in SDL

A directive is a named instruction that can accept arguments and be attached to defined locations. GraphQL has several standard type system directives, two common ones being:

- `@deprecated`: marks a field or enum value as no longer recommended; an optional reason can be provided.
- `@specifiedBy`: attaches a URL describing the contract of a custom scalar.

Example of marking an old field:

```graphql
type Book {
    id: ID!
    title: String!
    authorName: String @deprecated(reason: "Use author { name } instead.")
    author: Author
}
```

You can define custom directives in SDL:

```graphql
enum Role {
    USER
    EDITOR
    ADMIN
}

directive @requiresRole(role: Role!) on FIELD_DEFINITION

type Query {
    publicBooks: [Book!]!
    moderationQueue: [Book!]! @requiresRole(role: ADMIN)
}
```

The `on FIELD_DEFINITION` clause restricts where the directive may appear. GraphQL defines valid locations such as `OBJECT`, `FIELD_DEFINITION`, `ARGUMENT_DEFINITION`, `INPUT_FIELD_DEFINITION`, `SCALAR`, `ENUM_VALUE`, as well as executable document locations like `FIELD`, `QUERY`, or `FRAGMENT_SPREAD`.

Merely declaring a directive in SDL does not automatically enforce authorization or alter resolver behavior. The application must have a mechanism to read and apply the directive, such as schema wiring, instrumentation, or an appropriate security layer. With Spring Security, permission checks in services/resolvers remain essential; a directive should not be treated as a decorative label creating the illusion that a field is protected.

## 11. Schema descriptions and comments

SDL supports descriptions using strings placed before definitions or fields. Descriptions are preserved in the schema and can appear in introspection, documentation, or API explorer tools:

```graphql
"""A book that can be searched in the library."""
type Book {
    """Stable identifier of the book."""
    id: ID!

    """Display title for readers."""
    title: String!
}
```

Comments starting with `#` are useful for source-file notes but are not equivalent to schema descriptions. If an explanation is part of the API documentation intended for schema consumers, use a description rather than only writing a comment.

Descriptions should explain business meaning, units of measurement, null rules, or important constraints. Avoid simply restating the field name without adding useful information.

## 12. Extending types and splitting schemas across multiple files

As a schema grows, definitions can be split by business domain or type group. GraphQL SDL supports `extend` to add fields to an already defined type:

```graphql
# books.graphqls
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
```

```graphql
# authors.graphqls
type Author {
    id: ID!
    name: String!
}

extend type Query {
    author(id: ID!): Author
}

extend type Book {
    author: Author
}
```

`extend type` adds fields or interfaces to a type that already exists in the combined schema. The extended type must have an original definition, and the extension must contribute valid content; do not use empty extensions. Duplicate definitions are invalid if they create conflicts in the schema.

In a Spring Boot application using Spring for GraphQL, default schema resources are typically discovered under `classpath:graphql/**/` with `.graphqls` or `.gqls` extensions. You can organize them by domain, for example:

```text
src/main/resources/
└── graphql/
    ├── common.graphqls
    ├── books/
    │   ├── book-types.graphqls
    │   └── book-queries.graphqls
    └── authors/
        ├── author-types.graphqls
        └── author-queries.graphqls
```

These files are merged into a single schema; splitting files only helps organize source code and does not create separate schemas per folder. Therefore, type names, field names, and extensions must remain consistent across the entire resource set. If the project changes the schema location, the schema locations configuration must point to the resources to load.

## 13. From SDL to resolvers in Spring for GraphQL

SDL declares fields and return types. Resolvers provide values when GraphQL executes a field. Example schema:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
```

You can implement a resolver for a root field with a Spring controller:

```java
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
```

`@QueryMapping` binds the method to `Query.book`; `@Argument("id")` binds the argument declared in SDL. If field names, arguments, or data types between the schema and resolver are incompatible, schema wiring or execution may fail. Simple fields like `Book.id` and `Book.title` can be read by GraphQL Java from getters or record accessors without needing separate resolvers.

The schema also does not replace input validation, authorization, or resource limits. SDL can describe required arguments and data types, but rules such as whether a user has permission to read a book or how deep a query may go must be enforced on the server.

## 14. Validating schema correctness

Before running the application, ensure the schema can parse and build into a valid type system. Common errors include:

- Missing root `Query` or declaring the root type with the wrong name.
- Referencing an undefined type.
- Duplicate type, field, or enum value names.
- Using an output object type in an input position or vice versa.
- An object declaring `implements` while missing required fields or having incompatible types.
- A union containing a non-object type.
- A directive used at a location not listed in its `on` clause.
- An argument or default value incompatible with the declared type.

In Spring for GraphQL, schema initialization catches many structural and wiring errors early at application startup. You should have schema startup tests and integration tests sending real operations to detect mismatches between SDL and resolvers as well.

Example of an operation that the schema should accept:

```graphql
query FindBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
```

If the schema does not declare `book`, lacks the `id` argument, or has an incompatible argument type, GraphQL can reject the operation during validation before calling any resolver. This is a key benefit of a typed schema: many contract errors are caught before accessing data.

## 15. Designing schemas for evolution

A schema is a public contract between server and client. Schema changes should be evaluated for compatibility:

| Change | Typical impact |
| --- | --- |
| Adding a new nullable field to an object | Usually compatible with existing clients |
| Adding an optional argument with a default | Usually does not force old clients to modify requests |
| Adding a required argument without a default | Can make existing operations invalid |
| Removing or renaming a field/argument | Breaking change for clients currently using it |
| Changing a nullable output to non-null | Can cause errors if resolvers can still return null |
| Changing a nullable input to non-null | Old clients may no longer send valid requests |
| Adding an enum value | Can affect clients performing exhaustive enum handling |
| Removing an enum value | Breaking change if clients still send or handle that value |

When you need to replace a field, you can add the new field, mark the old one with `@deprecated`, update clients, and only remove it in an appropriate contract-change release. For example:

```graphql
type Book {
    id: ID!
    authorName: String @deprecated(reason: "Use author { name } instead.")
    author: Author
}
```

Do not change return or input types merely to make the schema shorter without checking existing data and API consumers. Schema diff tools and contract tests can help catch risky changes in CI pipelines.

## 16. Workflow for writing SDL for a new feature

When designing a GraphQL feature, you can follow this sequence:

1. Identify the operations clients need: reading, modifying, or subscribing to events.
2. Identify the object types and data relationships to expose.
3. Choose scalars, enums, input objects, interfaces, or unions according to each type's role.
4. Declare fields, arguments, default values, lists, and nullability per the business contract.
5. Write descriptions for important types and fields; use directives when they carry clear semantics.
6. Split files by domain and use `extend` when adding to root types or existing types.
7. Verify the schema builds cleanly, then wire resolvers and write operation tests.
8. Assess compatibility before changing any schema already consumed by clients.

SDL is the foundation of a GraphQL API: it clarifies what data is exposed, how clients query it, and what constraints the server must uphold. A good schema has clear types, intentional nullability, separated inputs and outputs, and can evolve without surprising clients. In Spring for GraphQL, keeping SDL consistent with resolvers and testing the schema during development keeps the API contract understandable, maintainable, and reliable.
