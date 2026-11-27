# List types in GraphQL SDL

A GraphQL List type represents a list of values of the same type. In Schema Definition Language (SDL), you enclose the element type in square brackets, such as `[Book]` or `[String]`. List types are commonly used to return multiple records from a query, represent multi-valued attributes, or accept a set of criteria from clients.

In Spring for GraphQL, List types are declared in the schema just like other GraphQL types. Java resolvers typically return `List<T>` or an equivalent `Collection<T>`. To design them properly, you must consider both layers: whether the list itself can be `null`, and whether individual elements inside the list can be `null`.

## 1. Basic List type syntax

A list type has the form `[Type]`, where `Type` is the type of each element:

```graphql
type Query {
    bookTitles: [String]
    books: [Book]
}

type Book {
    id: ID!
    title: String!
}
```

`bookTitles` returns a list of strings; `books` returns a list of `Book` objects. Every element in the list shares the same GraphQL type, though element values can differ.

List types can wrap scalars, enums, objects, interfaces, or unions in output positions. In input positions, the element type must be a valid input type such as a scalar, enum, or input object. For example, you cannot declare an argument of type `[Book]` if `Book` is an object type; create `input BookFilter` when you need to receive structured input data.

GraphQL lists preserve element order. Lists can also contain duplicate values. Therefore, when order and multiplicity matter to the API, Java's `List<T>` usually expresses the contract more clearly than `Set<T>`.

## 2. Combining List types with Non-Null

An `!` placed after a type means the value at that position cannot be `null`. For a list, there are two independent places to put `!`:

- After the element type, inside `[]`: governs whether individual elements can be `null`.
- After `]`: governs whether the list itself can be `null`.

Four common declarations:

| SDL | Can list be `null`? | Can elements be `null`? | Meaning |
| --- | --- | --- | --- |
| `[Book]` | Yes | Yes | The list may be absent; if present, individual elements may still be null. |
| `[Book]!` | No | Yes | Always returns a list, though the list may contain null elements. |
| `[Book!]` | Yes | No | The list may be null; if a list is returned, every element must have a value. |
| `[Book!]!` | No | No | Always returns a list and every element must have a value. |

Example:

```graphql
type Query {
    allBooks: [Book!]!
    optionalRecommendations: [Book!]
    booksWithOptionalEntries: [Book]!
}
```

`allBooks: [Book!]!` is a strict contract: the resolver must always return a non-null list containing no null elements. When no matching books exist, returning an empty list `[]` is valid. `optionalRecommendations: [Book!]` allows the entire field to have no value (`null`), while requiring every item to be non-null if a list is returned.

`null` and `[]` carry different meanings. `null` signals that the field has no value per the API contract; `[]` signals that a list result exists with zero elements. For a field declared non-null, the resolver must return a concrete value even when the list has no elements.

## 3. Nullability and error propagation

GraphQL enforces Non-Null constraints when completing each field's value. If a resolver returns `null` for a non-null field, or a `null` element appears where the element type is non-null, GraphQL raises an execution error and propagates `null` up to the nearest nullable ancestor.

For example, with the declaration:

```graphql
type Query {
    books: [Book!]!
}
```

if an element in `books` is `null`, the entire list cannot be completed because the element type is `Book!`. The `books` field also cannot be null due to the outer `!`, so `null` continues bubbling up to the parent. When the field sits directly on the root `Query`, `data` itself can become `null`.

If declared as `[Book!]` (nullable list), an error caused by a null element still turns the list into `null`, without necessarily breaking sibling fields on the parent object. That is why nullability must be chosen according to business semantics and the blast radius an element error could cause.

When designing a schema, answer two questions for every list field: is the absence of a list a valid state, and is a null element a valid state? Never add `!` merely to make a schema look strict; resolvers and real data must be able to uphold that contract.

## 4. Using List types for Queries and nested fields

Example of an API returning lists of books:

```graphql
type Query {
    books: [Book!]!
    booksByAuthor(authorId: ID!): [Book!]!
}

type Book {
    id: ID!
    title: String!
    tags: [String!]!
}
```

`books` and `booksByAuthor` both return lists of `Book`. The `tags` field is a list of strings inside each `Book` object. When a client requests:

```graphql
query {
    booksByAuthor(authorId: "author-42") {
        id
        title
        tags
    }
}
```

GraphQL returns a JSON array for each list field:

```json
{
  "data": {
    "booksByAuthor": [
      {
        "id": "book-1",
        "title": "GraphQL Basics",
        "tags": ["backend", "api"]
      },
      {
        "id": "book-2",
        "title": "Schema Design",
        "tags": []
      }
    ]
  }
}
```

The empty `tags` list on the second book is still valid for `[String!]!`: the list exists and no element violates the type. If a `tags` field returned `null`, the non-null contract would be violated.

## 5. Declaring List types in inputs

List types can also appear in field arguments or input objects. For example, a client wants to search for multiple books by IDs and tags:

```graphql
input BookSearchInput {
    ids: [ID!]!
    tags: [String!]
}

type Query {
    searchBooks(filter: BookSearchInput!): [Book!]!
}
```

Here, `ids` requires a list where each ID is non-null. `tags` may be omitted or null; if a list is provided, the tags inside cannot be null. If business rules require `tags` to always be present, you can change it to `[String!]!`.

The client passes variables as follows:

```graphql
query SearchBooks($filter: BookSearchInput!) {
    searchBooks(filter: $filter) {
        id
        title
    }
}
```

```json
{
  "filter": {
    "ids": ["book-1", "book-2"],
    "tags": ["backend", "spring"]
  }
}
```

GraphQL supports list input coercion: where a list is expected, a single value can be coerced into a single-element list. Even so, clients should consistently send arrays to keep requests readable and avoid confusion when scaling from one value to multiple values.

A default value for an input list can be declared using a list literal in SDL:

```graphql
type Query {
    booksByStatus(statuses: [BookStatus!] = [PUBLISHED]): [Book!]!
}

enum BookStatus {
    DRAFT
    PUBLISHED
    ARCHIVED
}
```

When a client omits `statuses`, GraphQL uses the default value `[PUBLISHED]`. If the client supplies an explicit value, that value is used according to GraphQL's coercion rules.

## 6. Mapping List types to Java with Spring for GraphQL

Spring for GraphQL uses GraphQL Java to execute the schema. For a list-typed field, a resolver can return `List<T>`, `Collection<T>`, or another value type that GraphQL Java can handle as a list. In Spring applications, `List<T>` is usually the simplest and clearest choice.

Example resolver for the `books` query:

```java
import java.util.List;

import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }
}
```

Assume `Book` is a Java type whose fields map to the `Book` object type in SDL. The method name `books` matches the `books` field on the root `Query` type; `@QueryMapping` registers the method as the data fetcher for that field.

To map a list field inside an object, you can use `@SchemaMapping`:

```java
import java.util.List;

import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookFieldController {

    private final TagService tagService;

    public BookFieldController(TagService tagService) {
        this.tagService = tagService;
    }

    @SchemaMapping(typeName = "Book", field = "tags")
    public List<String> tags(Book book) {
        return tagService.findNamesByBookId(book.id());
    }
}
```

The method takes the parent object `Book` and returns a list of strings for the `tags` field. If the method name matches the field name and the class name matches the GraphQL type, some `@SchemaMapping` attributes can be inferred by convention; explicit declarations make examples easier to follow.

For an input object, you can bind the argument to a Java record or class with matching properties:

```java
public record BookSearchInput(List<String> ids, List<String> tags) {}
```

```java
@QueryMapping
public List<Book> searchBooks(@Argument("filter") BookSearchInput filter) {
    return bookService.search(filter);
}
```

Property names and types of the Java input must be compatible with the fields of `BookSearchInput` in SDL. If the schema uses `ID`, the application can represent IDs as `String` or an appropriate domain ID type; keep the mapping consistent across resolvers.

## 7. Rules for handling lists in resolvers

When a schema declares `[Book!]!`, resolvers must ensure two conditions: never return `null` for the list itself, and never let `null` elements enter the result. Example:

```java
@QueryMapping
public List<Book> books() {
    List<Book> result = bookService.findAll();
    return result == null ? List.of() : result;
}
```

The snippet above illustrates ensuring the outer list is non-null. In clean service design, `findAll()` should explicitly establish that no results yields an empty list. If underlying data can contain null elements, address the root cause in the domain or service layer rather than silently returning schema-violating data.

Practical guidelines:

- Return `[]` when a query succeeds with no matching elements.
- Return `null` only if the field is declared nullable and business logic genuinely has a state represented by null.
- Never return null elements for a list with a non-null element type.
- Preserve stable ordering when order matters to clients; use `ORDER BY` or intentional sorting in the query layer.
- Do not switch to `Set` if the API must preserve duplicates or source ordering.
- Control list sizes and provide pagination for large datasets.

GraphQL does not automatically cap the maximum number of elements in a list field. If a query could return tens of thousands of items, the server may spend excessive memory and serialization time. Design pagination, page size limits, and query depth or complexity controls according to system requirements.

## 8. List types and the N+1 problem

A list field can expose the N+1 problem when a child resolver queries data for each element individually. For example, `books` returns 100 books and the `Book.tags` resolver runs a separate query per book. A single request then triggers 1 query for books plus 100 queries for tags.

In such cases, batch data loading using `@BatchMapping` or `DataLoader`. The implementation must align results back to each parent object while preserving the SDL type contract. A List type only describes the shape of data clients receive; it does not automatically optimize database access counts.

When working with nested lists, consider both the size of each list and how many times resolvers are invoked. A query asking for many books, each with many authors and many tags, can generate huge payloads even within a single HTTP request.

## 9. Testing fields that return lists

Tests should verify element count, values, and nullability contracts. Example using a `GraphQlTester` configured in the test context:

```java
@Test
void booksReturnsAnOrderedList() {
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
}
```

Beyond item count, test ordering when the API guarantees ordering, test `[]` when no data exists, and test error behavior when a resolver produces values violating Non-Null. For nullable fields, explicitly test the `null` case if it is a valid business state.

Example of testing an input list by sending multiple IDs:

```java
@Test
void searchBooksAcceptsSeveralIds() {
    graphQlTester.document("""
            query Search($filter: BookSearchInput!) {
                searchBooks(filter: $filter) { id }
            }
            """)
        .variable("filter", java.util.Map.of("ids", List.of("book-1", "book-2")))
        .execute()
        .path("searchBooks")
        .entityList(BookIdView.class)
        .hasSize(2);
}
```

The `BookView` and `BookIdView` classes in the examples are test DTOs with properties matching the selection sets. Tests should set up fixed fixture data so results are predictable and repeatable.

## 10. Nested lists

GraphQL allows a list to contain other lists. Example:

```graphql
type Query {
    scoreMatrix: [[Int!]!]!
}
```

`[[Int!]!]!` means the outer list is non-null, each inner list is non-null, and each integer is non-null. A valid response might be:

```json
{
  "data": {
    "scoreMatrix": [
      [8, 9, 10],
      [7, 8, 9]
    ]
  }
}
```

Nested lists fit matrix-like structures or grouped collections. For complex business data, consider named object types instead of deeply nested lists; objects give each component clear semantics and dedicated fields, making evolution easier.

## 11. Common mistakes when using List types

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| Field declared `[Book!]!` returns null | Resolver or service returns null when no data is found | Standardize on returning an empty list, or update the schema if null is valid. |
| Entire list field becomes null when one element fails | Element violates `Book!`; null propagates per the Non-Null contract | Validate element data and choose appropriate nullability. |
| Cannot pass an object as an input list | Using an output object type in an input position | Declare an `input` type and use `[InputType]` for lists of input objects. |
| Unstable element ordering | Database query lacks `ORDER BY` or uses an unordered collection | Sort results according to the API's published criteria. |
| Oversized request or response | List lacks size limits or pagination | Add pagination and cap page sizes. |
| Database query count scales with element count | Child field resolver queries separately for each object | Use `@BatchMapping`, `DataLoader`, or batch queries. |

## 12. Checklist for designing List types

1. Choose the right element type: scalar, enum, object, or input object depending on position.
2. Decide independently whether the list and individual elements may be null.
3. Use `[T!]!` when the API must always return a list with valid items; return `[]` when empty.
4. Use Java `List<T>` or a suitable collection for resolver mapping, preserving order and nullability per SDL.
5. Use input objects when passing a structured group of criteria.
6. Design pagination and size limits for large lists.
7. Check for N+1 risks when elements have fields requiring extra data loading.
8. Test populated lists, empty lists, ordering, and null/error scenarios.

List types allow GraphQL to represent multi-element data consistently in both inputs and outputs. Combined properly with Non-Null, Java mappings, and data-loading strategies, the schema clearly communicates what clients can receive or send while helping the server catch API contract violations early.
