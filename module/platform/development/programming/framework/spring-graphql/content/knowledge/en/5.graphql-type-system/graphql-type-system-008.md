# Type extension

GraphQL SDL lets you extend an already-declared type using the `extend` syntax. Type extensions allow splitting a schema across multiple files or domain modules while still forming **a single unified GraphQL schema** when the application starts. For example, a books module can declare the base `Query` and `Book` types, while a search module adds a `booksByAuthor` field to `Query` using `extend type Query`.

Type extension is part of the GraphQL Schema Definition Language. It modifies the schema definition built from SDL—it does not modify Java classes, does not automatically create resolvers, and is not a mechanism for dynamically updating a running schema. In Spring for GraphQL, SDL files are discovered via the configured schema locations and then combined to build the schema executed by GraphQL Java.

## 1. Why use type extensions?

In a small schema, all types can live in a single file. As an API grows, a single file quickly becomes long and hard to divide ownership across teams. Splitting SDL by domain lets development teams manage each part independently:

```text
src/main/resources/graphql/
├── common/
│   └── scalars.graphqls
├── catalog/
│   ├── catalog.graphqls
│   └── catalog-search.graphqls
└── account/
    ├── account.graphqls
    └── account-profile.graphqls
```

The file `catalog.graphqls` can define the base types:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
```

The file `catalog-search.graphqls` adds search-related fields:

```graphql
extend type Query {
    booksByAuthor(authorId: ID!): [Book!]!
}
```

After the files are merged, `Query` contains both `book` and `booksByAuthor`. Clients see only one `Query` type; they do not need to know which file declared each field.

If you write another `type Query` definition with the same name as if it were a new type, the schema can fail with a duplicate definition error. When the goal is to add fields to an existing type, you must use `extend type Query`.

## 2. Syntax and general rules

The general syntax of a type extension is:

```graphql
extend type TypeName {
    newField: ReturnType
}
```

The `extend` keyword tells the parser that this is an addition to an existing definition. The name and type kind must match the base type. For instance, `extend type Book` can only extend an object type named `Book`; it cannot extend an enum or input object with that name.

Important rules:

- The extended type must exist in the combined schema and must match the type kind.
- The extension only adds new members; it must not redeclare existing fields, enum values, or union members.
- Types referenced by new fields must also exist in the combined schema after merging all files.
- After merging definitions and extensions, the entire schema must still pass GraphQL's validation rules.
- Multiple extensions may target the same type, provided the additions do not conflict and the final schema is valid.

Type extension is not a way to override a field. If you need to change the return type or arguments of an existing field, edit the base definition and assess API compatibility impact.

## 3. Extending object types

`extend type` is commonly used to add fields to an object type. You can add simple fields, fields with arguments, list-returning fields, or fields referencing other types:

```graphql
type Book {
    id: ID!
    title: String!
}

type Author {
    id: ID!
    name: String!
}

extend type Book {
    author: Author
    relatedBooks(limit: Int = 5): [Book!]!
}
```

After extension, `Book` has the fields `id`, `title`, `author`, and `relatedBooks`. `author` can return `null`; `relatedBooks` must return a non-null list with no null elements.

An object type extension can also add interfaces implemented by the object type:

```graphql
scalar DateTime

interface Node {
    id: ID!
}

type Book {
    id: ID!
    title: String!
}
```

In this example, `Book` already has an `id` field compatible with the `Node` interface, so the interface implementation can be added. If the interface has a field that the object does not yet provide with the right type and argument rules, schema validation will fail. An extension can add both an interface and new fields in the same block:

```graphql
extend type Book implements Node {
    publishedAt: DateTime
}
```

## 4. Extending interfaces

An interface describes a set of fields that implementing object types must provide. You can add fields to an interface using `extend interface`:

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

extend interface Node {
    createdAt: DateTime!
}
```

When adding `createdAt` to `Node`, every object type implementing `Node` in the final schema must also have a compatible `createdAt` field. Therefore, an interface extension has a broader impact than simply adding a field to a single object type. All related implementations must be updated or verified before the schema can be built successfully.

Example of updating object types to satisfy the extended interface:

```graphql
extend type Book {
    createdAt: DateTime!
}

extend type Author {
    createdAt: DateTime!
}
```

If you cannot ensure that every implementation provides the new field, consider adding the field to individual object types instead of extending the shared interface. That decision depends on the contract clients need to rely on.

## 5. Extending unions

A union represents a result that can belong to one of several object types. `extend union` lets you add object types to its member set:

```graphql
type Book {
    id: ID!
    title: String!
}

type Author {
    id: ID!
    name: String!
}

union SearchResult = Book | Author

type Magazine {
    id: ID!
    issue: Int!
}

extend union SearchResult = Magazine

type Query {
    search(keyword: String!): [SearchResult!]!
}
```

After the extension, `SearchResult` can contain `Book`, `Author`, or `Magazine`. Clients must use inline fragments to fetch type-specific fields:

```graphql
query {
    search(keyword: "GraphQL") {
        ... on Book {
            title
        }
        ... on Author {
            name
        }
        ... on Magazine {
            issue
        }
    }
}
```

Union members must be object types. You cannot add a scalar, enum, or interface directly as a union member. Adding a new member can affect clients using code generation or exhaustive result handling; clients should include a fallback branch for unknown result types.

## 6. Extending enums

An enum restricts a value to a declared set of names. `extend enum` adds new values to that set:

```graphql
enum BookStatus {
    DRAFT
    PUBLISHED
}

extend enum BookStatus {
    ARCHIVED
    OUT_OF_PRINT
}
```

The final schema allows `BookStatus` to take four values. New enum values must not duplicate values already declared in the base enum or in another extension.

Adding an enum value is generally an additive change on the schema side, but clients may need code updates. Some clients generate enums as closed types and use `switch` statements that may not yet handle the new value. When evolving a public API, consider how clients handle unrecognized enum values.

## 7. Extending input objects

`extend input` adds fields to an existing input object:

```graphql
enum BookStatus {
    DRAFT
    PUBLISHED
}

input BookFilter {
    keyword: String
    status: BookStatus
}

extend input BookFilter {
    authorId: ID
    publishedAfter: DateTime
}
```

Clients can pass the new fields in the input object:

```graphql
query {
    books(filter: {
        status: PUBLISHED
        authorId: "author-01"
    }) {
        id
        title
    }
}
```

When extending an input object already used by clients, pay special attention to new fields with non-null types. Adding a required field without a default value can turn requests from older clients that omit that field into invalid requests. For a more compatible change, prefer adding nullable fields or providing a business-appropriate default value.

## 8. Extending scalars

A scalar describes a single value such as a string, number, or domain-specific type. `extend scalar` can attach directives to an already-declared scalar:

```graphql
scalar DateTime

extend scalar DateTime @specifiedBy(
    url: "https://scalars.graphql.org/andimarek/date-time"
)
```

This extension adds metadata about the format used by the scalar. It does not change how Java parses input or serializes output. For custom scalars such as `DateTime`, the application still needs to configure appropriate `Coercing` in GraphQL Java's runtime wiring or the corresponding Spring for GraphQL configuration mechanism.

Scalar extension is not a mechanism for adding fields to a scalar or changing the data type inside a scalar. If you need to change serialization/coercion behavior, update the runtime scalar implementation and test compatibility.

## 9. Schema extensions and type extensions

`extend schema` has its own syntax for adding operation types or directives applied to the schema itself. It differs from `extend type`, which extends a specific object type.

For example, a base schema declares the query root:

```graphql
schema {
    query: Query
}

type Book {
    id: ID!
}

type Query {
    book(id: ID!): Book
}

type Mutation {
    renameBook(id: ID!, title: String!): Book!
}
```

Another file can add the mutation root to the declared schema:

```graphql
extend schema {
    mutation: Mutation
}
```

After merging, the schema has both a query root and a mutation root. Operation roots are configured at the schema level, whereas fields like `renameBook` are defined inside the `Mutation` object type. Do not confuse `extend schema` with `extend type Mutation`: the first adds an operation type to the schema, while the second adds fields to the `Mutation` object type.

## 10. Combining multiple SDL files in Spring for GraphQL

Spring Boot can scan for schema files on the classpath, typically under `src/main/resources/graphql/`. Example configuration:

```yaml
spring:
  graphql:
    schema:
      locations: classpath:graphql/**/
```

Suppose the files are organized as follows:

```text
src/main/resources/graphql/
├── core/
│   └── schema.graphqls
└── catalog/
    ├── catalog.graphqls
    └── search.graphqls
```

`schema.graphqls` can define `Query` and shared types. `catalog.graphqls` defines `Book`, while `search.graphqls` uses `extend type Query` to add search fields. Spring for GraphQL loads resources from the configured locations, combines type definitions and extensions, and builds a `GraphQlSource` containing the complete schema for GraphQL Java.

Crucially, all loaded files together must form a valid schema. Finding files at the resource path does not guarantee valid SDL contents; base types must still exist, fields must not be duplicated, and interface/union relationships must satisfy type system rules.

## 11. Type extensions do not automatically create resolvers

An SDL extension only adds to the contract. If you extend `Query` with a `booksByAuthor` field, the application still needs to supply how data is fetched for that field. With Spring for GraphQL, you can declare a controller:

```java
@Controller
public class BookSearchController {

    private final BookService bookService;

    public BookSearchController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> booksByAuthor(@Argument String authorId) {
        return bookService.findByAuthorId(authorId);
    }
}
```

New fields on `Book` also need resolvers if they cannot be read from the source object via the default property fetcher:

```java
@Controller
public class BookAuthorController {

    private final AuthorService authorService;

    public BookAuthorController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }
}
```

Spring discovers mapping methods in controller beans and wires them to fields in the runtime schema. If the SDL has a field without a resolver and the source object lacks a matching property, queries may return `null` or unexpected data depending on the field type and default fetching behavior.

## 12. Validation rules and common errors

GraphQL validates the schema after combining base definitions and extensions. Some common errors:

| Error | Cause | How to resolve |
| --- | --- | --- |
| `Cannot extend type ... because it is not defined` | Base type was not loaded or name is misspelled | Check the file defining the type and schema locations |
| Extending the wrong kind of type | Using `extend type` for an enum/interface/input or vice versa | Use the matching extension keyword |
| Duplicate field definition | Extension redeclares an existing field | Remove the duplicate field or edit the base definition |
| Duplicate enum value | Multiple files add the same value | Declare each enum value only once |
| Duplicate or non-object union member | Member already exists or references the wrong type kind | Check the union members list |
| Interface has new field not implemented by object | Implementations no longer satisfy the interface contract | Update affected object types or redesign the interface |
| Input object has new required field | Older clients omit the new field | Consider making it nullable or adding a default value |
| Valid schema but field fails to fetch data | No matching resolver registered | Add `@QueryMapping`, `@SchemaMapping`, or the appropriate mapping |

SDL parse/validation errors usually prevent the application from building the schema at startup. When that happens, check base type names, matching extension kinds, duplicate fields/members, and relationships between interfaces and object implementations. If the schema starts up but a field returns wrong data, inspect the resolver and data source rather than editing extension syntax.

## 13. Designing safe extensions as a schema evolves

Split files by domain and designate one owner for each type's base definition. Other domains only add fields via extensions, avoiding multiple teams editing or redeclaring base fields. Use consistent field names and validate the full schema after adding extensions.

Assess the impact of each kind of change:

- Adding a nullable field to an object type is usually the least disruptive extension for existing clients.
- Adding a field to an interface affects every object type implementing that interface.
- Adding an enum value or union member may require clients to handle the new case.
- Adding a non-null input field without a default can invalidate existing client operations.
- Changing the return type, arguments, or nullability of an existing field can break the published contract.

Type extensions help organize schemas by module and domain, without relaxing the consistency rules of the GraphQL type system. All files must still combine into a valid schema, every published field needs an appropriate way to resolve data, and all contract changes should be evaluated alongside active API clients.
