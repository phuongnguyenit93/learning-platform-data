# Schema documentation with descriptions

A GraphQL schema shows what types, fields, arguments, and return types an API exposes. However, a field like `Book.status: BookStatus!` does not explain which states can appear, when a book is considered `ARCHIVED`, or what a client should do when encountering that value. To turn a schema into a self-explanatory contract, GraphQL SDL supports **descriptions** on schema elements.

A description is a text string attached directly to definitions of types, fields, arguments, enum values, input fields, scalars, directives, and other eligible schema elements. GraphQL includes these descriptions in introspection, enabling tools such as GraphiQL, IDEs, and API documentation generators to display documentation without reading server-side Java source code.

In Spring for GraphQL, schemas are typically declared with SDL inside `src/main/resources/graphql/`. Therefore, API documentation should be written right alongside the SDL definitions it explains. This lesson covers description syntax, querying descriptions via introspection, distinguishing descriptions from comments and deprecations, and guidelines for writing documentation that helps clients.

## 1. Descriptions are part of the GraphQL schema

GraphQL SDL allows placing a string literal immediately before the definition it documents. Example:

```graphql
"""
Public information of a book in the library.
Fields in this type are used for list and detail screens.
"""
type Book {
  """Stable identifier of the book."""
  id: ID!

  """Title displayed to readers."""
  title: String!

  """Publication year; may be absent for unpublished materials."""
  publishedYear: Int
}
```

The description string precedes the definition it describes. In the example, the first description belongs to `Book`; subsequent descriptions belong to each individual field. When the schema is parsed, GraphQL preserves these descriptions in the schema metadata.

Descriptions do not alter how resolvers run and do not change data types. They add semantics to the API contract so consumers know what a field represents, what values it can hold, and how it should be used.

## 2. Writing single-line and multi-line descriptions

GraphQL supports two forms of string literals commonly used for descriptions.

### Single-line strings

Strings enclosed in double quotes suit short descriptions:

```graphql
type Author {
  "Display name of the author."
  name: String!
}
```

If the content contains double quotes or special characters, escape them using GraphQL string syntax. Do not use single quotes in place of double quotes.

### Multi-line block strings

Block strings are enclosed in triple double quotes. This form suits multi-sentence descriptions, such as explaining business semantics or usage conditions:

```graphql
"""
A book in the library catalog.

`Book` represents an item that can be searched and displayed.
The `author` field may be absent if author data has not been linked yet.
"""
type Book {
  id: ID!
  title: String!
  author: Author
}
```

GraphQL normalizes block string indentation so formatting spaces used in SDL do not become extra content in the description. Even so, write clean block strings with blank lines between paragraphs and avoid unnecessary leading or trailing whitespace.

You can use light Markdown inside description text if display tools support it, such as wrapping field names in backticks or using short lists. However, the canonical value returned by introspection is still a plain string; not every client renders Markdown identically. Ensure descriptions remain clear even when displayed as plain text.

## 3. Describing types, fields, and arguments

A useful description answers the question clients have at the exact point of use. Describe types at a high-level concept level, fields at the data-meaning level, and arguments at the parameter-passing level.

```graphql
"""
Information about an author whose books are stored in the library.
"""
type Author {
  "Identifier of the author."
  id: ID!

  "Name used for display and search."
  name: String!

  """
  Books by the author.

  The list is paginated by `first`; results exclude deleted books.
  """
  books(
    "Maximum number of books to return in one call; defaults to 10."
    first: Int = 10
  ): [Book!]!
}
```

An argument's description sits directly before the argument inside the field's parentheses. This is especially helpful when a field accepts multiple parameters such as filters, sorting, pagination, or optional flags.

When writing descriptions for fields with arguments, explain:

- Units of measurement, such as seconds, minutes, currency, or item count.
- Valid value ranges and default values.
- The effect of omitting an argument versus passing `null`, if they differ.
- Pagination, sorting, or filtering rules clients need to know.

Filter example:

```graphql
type Query {
  """
  Search for books by optional criteria.

  Criteria are combined with AND. If no filter is provided,
  the API returns books ordered by most recently updated.
  """
  books(
    "Book filter criteria. Can be omitted to fetch the default list."
    filter: BookFilter
  ): [Book!]!
}

input BookFilter {
  "Keyword matched against the title, case-insensitively."
  keyword: String

  "Return only books in the specified status."
  status: BookStatus
}
```

Descriptions must match actual resolver behavior. If a description claims filters combine with AND while the implementation uses OR, the documentation will mislead client integration even though the schema validates cleanly.

## 4. Describing input objects and input fields

Input objects are commonly used in mutations or filters. Descriptions at the input type level help clients understand the purpose of the data group; descriptions on individual input fields explain requirements and rules for each value.

```graphql
"""
Data required to create a book.

The server generates `id` and creation timestamp automatically. Clients do not send these values.
"""
input CreateBookInput {
  "Book title; must not be blank after trimming whitespace."
  title: String!

  "ID of an existing author in the library."
  authorId: ID!

  "Initial status; defaults to DRAFT if omitted."
  status: BookStatus = DRAFT
}

type Mutation {
  "Create a new book and return the persisted record."
  createBook(input: CreateBookInput!): Book!
}
```

The description of `title` states a business rule that `String!` alone cannot express: the string cannot be blank after trimming. Non-null only prevents `null`; it does not prevent empty strings or whitespace-only strings. The server must still validate inputs in code.

Similarly, `authorId: ID!` ensures the client passes a non-`null` ID, but does not ensure that the author exists or that the caller has permission to link that author to a book. Descriptions should clarify meaning and key validation rules while the server enforces them.

## 5. Describing enums, scalars, interfaces, and directives

### Enums and individual enum values

Enums model a finite domain of values. Each value should carry a description if its business meaning is not self-evident:

```graphql
"Lifecycle status of a book."
enum BookStatus {
  "Book is being edited and is not publicly visible yet."
  DRAFT

  "Book has been published and can be searched."
  PUBLISHED

  "Book is no longer in circulation but remains in history."
  ARCHIVED
}
```

The enum description explains the overall domain; each enum value description explains behavioral differences. This helps clients build appropriate filters, status badges, or workflows.

### Scalars

Custom scalars should document format, units, timezone, and parse/serialize rules:

```graphql
"""
Timestamp in ISO-8601 format, including timezone offset.

Example: `2026-11-20T09:30:00+07:00`.
"""
scalar DateTime
```

Include an example only if the custom scalar actually accepts that format. Descriptions do not register the scalar at runtime and do not replace the coercing implementation.

### Interfaces and unions

Interfaces can describe the shared contract of implementing types. Interface fields can also have descriptions:

```graphql
"An item that can appear in search results."
interface SearchResult {
  "Identifier of the result."
  id: ID!

  "Title displayed in search result lists."
  title: String!
}

"A search result representing either a book or an author."
union SearchItem = Book | Author
```

For unions, a union-level description helps clients understand which object types may appear. Member object types still need their own descriptions to explain specific fields.

### Custom directives

Directives can be documented alongside their arguments:

```graphql
"Marks a field as intended for internal clients only."
directive @internalOnly(
  "Reason why access to the field is restricted."
  reason: String
) on FIELD_DEFINITION
```

Descriptions explain the directive's purpose, but do not implement security behavior automatically. To restrict access, the server must enforce corresponding logic via wiring, instrumentation, interceptors, or an appropriate authorization mechanism.

## 6. Distinguishing descriptions from comments in SDL

GraphQL SDL also supports comments starting with `#`. Comments are useful for notes aimed at readers of the schema file, but comments are not schema element descriptions and are not returned by introspection.

```graphql
# This is an SDL file comment. Introspection tooling does not receive this text.
type Book {
  "This description is attached to the field and can be returned by introspection."
  title: String!
}
```

| Criterion | `#` Comment | Description string |
| --- | --- | --- |
| Purpose | Notes for readers of the SDL file | API schema documentation |
| Syntax | `# text` | String literal placed before a definition |
| Attached to type/field | No | Yes |
| Exposed via introspection | No | Yes |
| Shown in schema tooling | Usually no | Yes, when tooling supports it |

Do not use comments instead of descriptions if clients, GraphiQL, or documentation generators need access to the content. Conversely, comments remain appropriate for internal implementation notes outside the API contract.

## 7. Querying descriptions via introspection

GraphQL introspection lets clients query the schema for types, fields, arguments, enum values, and their descriptions. The `description` fields on introspection types return the text declared in SDL.

Example querying descriptions of the `Book` type and its fields:

```graphql
query BookDocumentation {
  __type(name: "Book") {
    name
    description
    fields {
      name
      description
      args {
        name
        description
      }
    }
  }
}
```

Abbreviated response:

```json
{
  "data": {
    "__type": {
      "name": "Book",
      "description": "Public information of a book in the library. Fields in this type are used for list and detail screens.",
      "fields": [
        {
          "name": "id",
          "description": "Stable identifier of the book.",
          "args": []
        },
        {
          "name": "title",
          "description": "Title displayed to readers.",
          "args": []
        }
      ]
    }
  }
}
```

To inspect descriptions and deprecation status of enum values:

```graphql
query BookStatusDocumentation {
  __type(name: "BookStatus") {
    name
    description
    enumValues(includeDeprecated: true) {
      name
      description
      isDeprecated
      deprecationReason
    }
  }
}
```

Introspection is useful for tooling and documentation checks. However, servers may configure policies restricting introspection in production environments. Disabling introspection does not remove descriptions from the loaded schema; it only prevents clients from querying metadata via introspection at that endpoint.

## 8. Descriptions vs. deprecation

Descriptions explain the current meaning and usage of an element. Deprecation notifies clients that an element is outdated and recommends migrating to an alternative.

GraphQL has the standard `@deprecated` directive, applicable to fields and enum values:

```graphql
type Book {
  "Current book identifier."
  id: ID!

  "Legacy code retained for compatibility with previous client versions."
  legacyCode: String @deprecated(reason: "Use `id` instead.")
}

enum BookFormat {
  PAPERBACK
  HARDCOVER
  PRINTED @deprecated(reason: "Use PAPERBACK or HARDCOVER.")
}
```

In introspection, clients can read `isDeprecated` and `deprecationReason`. Descriptions and deprecation reasons serve different purposes:

- Descriptions explain what a field does and what the data means.
- `@deprecated` signals that clients should stop using the field or enum value.
- `reason` explains why it was deprecated or suggests a replacement.

Do not use deprecation as a substitute for removing a field overnight. A safe rollout typically involves publishing the new field, marking the old field deprecated, updating clients, monitoring usage, and removing the old field only under the API's versioning/compatibility policy.

## 9. How descriptions are used in Spring for GraphQL

Spring for GraphQL typically uses schema-first development: Spring Boot loads `.graphqls` or `.gqls` files, builds `GraphQlSource`, and wires the schema to controller resolvers. Descriptions are parsed alongside SDL and retained in the runtime schema.

Example file `src/main/resources/graphql/book.graphqls`:

```graphql
"Book information displayed in the library."
type Book {
  "Server-managed book identifier."
  id: ID!

  "Book title."
  title: String!
}

type Query {
  "Find a book by ID. Returns null if not found."
  book(id: ID!): Book
}
```

The Java resolver only needs to map fields by name and supply data:

```java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }
}
```

No extra annotation is needed on Java methods for SDL descriptions to appear. Descriptions belong to the schema; `@QueryMapping` simply binds `Query.book` to the Java method. Changing a description while keeping the field name and type unchanged requires no resolver code changes.

You can verify descriptions with `GraphQlTester` via introspection:

```java
graphQlTester.document("""
        query {
            __type(name: "Book") {
                name
                description
                fields {
                    name
                    description
                }
            }
        }
        """)
    .execute()
    .path("__type.description")
    .entity(String.class)
    .isEqualTo("Book information displayed in the library.");
```

This test confirms the description was loaded into the runtime schema rather than merely checking that the SDL file contains a string. If the application restricts introspection, test the schema in an appropriate test context or use an allowed internal inspection mechanism.

## 10. Principles for writing quality descriptions

A good description lets clients use the API properly without reading server source code or asking the backend team about every field.

### Write from the client's perspective

Describe what the data means to clients, not internal implementation details. Examples:

| Weak description | Better description |
| --- | --- |
| `Get book.` | `Find a book by ID. Returns null if not found.` |
| `Author name.` | `Display name of the author, used on book cards and search results.` |
| `Count.` | `Maximum number of books returned per page; default value is 20.` |
| `Status.` | `Lifecycle status of the book: DRAFT, PUBLISHED, or ARCHIVED.` |

### State constraints and rules explicitly

If a field has special rules, state them clearly. For example, `price: Decimal!` does not tell clients the currency unit, whether tax is included, or how values are rounded. If those rules affect clients, document them in the description of the field or its enclosing type.

### Do not repeat information already conveyed by the type

For `id: ID!`, a description like `Book identifier` may suffice. Do not write wordy prose just to remind readers the field is required; `!` already states that. Use descriptions to explain business meaning, formats, or behaviors that types cannot express.

### Keep descriptions consistent with resolvers

If a description states a list is sorted by descending timestamp, the resolver must enforce that ordering. If a description says `null` means not found, do not also return `null` for insufficient permissions if clients need to distinguish the two cases. Incorrect documentation can be worse than missing documentation because clients build logic around it.

### Use consistent terminology

Pick one term for each domain concept and use it across the entire schema. For instance, if the API uses `author`, do not switch to `writer` elsewhere simply because it sounds more natural. Descriptions can mention synonyms if helpful, while type and field names stay stable.

## 11. Checklist when reviewing schema documentation

Before finalizing an SDL change, verify:

- Important types have descriptions explaining their role in the API.
- Non-obvious field names have clear descriptions of meaning and units.
- Arguments document default behaviors, valid ranges, and pagination rules.
- Input fields note important business validation rules.
- Enum values have descriptions sufficient for clients to distinguish states.
- Custom scalars specify format, timezone, units, and valid examples.
- Legacy fields/types are marked `@deprecated` with a reason and replacement suggestion.
- Descriptions do not contradict nullability, default values, or resolver behavior.
- Content meant for clients is written as descriptions, not only `#` comments.
- Introspection/tooling in the test environment displays the expected descriptions.

## 12. Hands-on exercise

Add documentation to a library schema:

1. Write descriptions for `Book`, `Author`, `BookStatus`, and `CreateBookInput`.
2. Describe `Book.id`, `Book.title`, `Book.author`, and the `Query.books(first:)` argument.
3. Describe each enum value of `BookStatus` so clients know when a book is in that state.
4. Apply `@deprecated` to `Book.oldTitle` and name the replacement field in the reason.
5. Write an introspection query to read descriptions for `Book`, the `title` field, and enum values.
6. Write a `GraphQlTester` test verifying that the `Book` type description matches the SDL.

Your schema starting point might look like this:

```graphql
"""Book information managed in the library."""
type Book {
  """Stable identifier of the book."""
  id: ID!

  """Official title used for display."""
  title: String!

  """Legacy title retained for compatibility with earlier clients."""
  oldTitle: String @deprecated(reason: "Use `title` instead.")
}
```

When finished, open GraphiQL or run the introspection query and confirm the descriptions appear in the runtime schema. The goal is for a new client to understand the meaning, constraints, and usage of the API from the schema alone without reading Java implementation code.
