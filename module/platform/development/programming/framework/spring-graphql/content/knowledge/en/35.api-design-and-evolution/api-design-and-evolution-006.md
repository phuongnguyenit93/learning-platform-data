# Changing Nullability in a GraphQL Schema

Nullability is part of the GraphQL contract between server and client. The `!` mark in SDL indicates that a value cannot be `null`; changing this mark can alter returned data, input requirements, or how errors propagate in the response. Therefore, changing nullability must be treated as an API change affecting both clients and resolvers.

GraphQL makes fields nullable by default. Non-Null should only be declared when the server can guarantee that a value is always present in every valid situation. In Spring for GraphQL, SDL defines this contract; resolvers and services must uphold that commitment.

## What does nullability mean in GraphQL?

In SDL, a type without `!` is nullable. A type with `!` is Non-Null:

```graphql
type User {
  id: ID!
  displayName: String
  manager: User
}
```

`id` must always have a value when the field is requested. `displayName` and `manager` may return `null`. If the client does not select a field, that field does not appear in the response; if the client selects a nullable field and the server has no value, the response includes the field with a `null` value.

Do not conflate `null` with an empty string, an empty list, or an unselected field:

| Value | Meaning |
| --- | --- |
| `null` | No value exists or no value can be provided per field semantics. |
| `""` | A string exists, and it is empty. |
| `[]` | A valid list exists with zero elements. |
| Field omitted | The client did not request the field or a directive skipped it. |

Non-Null does not mean the field always has data in the database. It is an API-level commitment: when the field is requested, the server must return a non-null value; if it fails to do so, GraphQL produces an execution error.

## Nullability of lists and list elements

For lists, `!` can apply to the list itself or to each element. These two positions are independent:

| SDL | Can list be null? | Can element be null? | Example valid values |
| --- | --- | --- | --- |
| `[Book]` | Yes | Yes | `null`, `[]`, `[null]`, `[book]` |
| `[Book]!` | No | Yes | `[]`, `[null]`, `[book]` |
| `[Book!]` | Yes | No | `null`, `[]`, `[book]` |
| `[Book!]!` | No | No | `[]`, `[book]` |

Example:

```graphql
type Author {
  booksA: [Book]
  booksB: [Book]!
  booksC: [Book!]
  booksD: [Book!]!
}
```

`booksB` guarantees a list is always returned, though the list may still contain null elements. `booksC` allows the entire list to be null, while disallowing null elements. `booksD` guarantees both the list and every element are non-null.

`[Book!]!` still permits `[]`. GraphQL Non-Null only forbids null values; it cannot express that a list must contain at least one element. If business rules require a non-empty list, validate in the service or use a payload type with status and data fields.

## Null propagation when a resolver violates Non-Null

When a resolver returns `null` for a Non-Null field, GraphQL produces an execution error and bubbles the null value up to the parent response position. This continues until a nullable position is reached; if no nullable position exists before the root, the entire `data` becomes null.

Example schema:

```graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  author: Author!
}

type Author {
  id: ID!
  name: String!
}
```

If `book` exists but the `author` resolver returns null, GraphQL cannot return `author: null` because the field is `Author!`. The error path points to `book.author`, while `book` becomes null because it is the nearest nullable parent:

```json
{
  "data": {
    "book": null
  },
  "errors": [
    {
      "message": "Cannot return null for non-nullable field Book.author.",
      "path": ["book", "author"]
    }
  ]
}
```

If `Query.book` is also `Book!`, null continues propagating to the root and the response has `data: null`. This is why changing a field from nullable to Non-Null can wipe out far more data than just the failing field.

### Nulls inside lists

With `books: [Book]`, a null element is preserved at its position:

```json
{
  "data": {
    "books": [
      { "id": "book-1" },
      null,
      { "id": "book-3" }
    ]
  }
}
```

With `books: [Book!]`, a null element violates the Non-Null item type. GraphQL generates an error and the entire list becomes null; because the list itself is nullable, the response can still preserve other fields:

```json
{
  "data": {
    "books": null
  },
  "errors": [
    {
      "message": "Cannot return null for non-nullable list item.",
      "path": ["books", 1]
    }
  ]
}
```

With `books: [Book!]!`, an element failure makes the list null, and the list's Non-Null then propagates null up to the parent. When designing list types, consider the desired failure isolation: allowing null items can preserve the remaining items; requiring non-null items can wipe out the whole list when one element fails.

## Nullability of output fields and inputs

Non-Null rules differ between returned data and client-supplied data:

| Position | Nullable | Non-Null (`!`) |
| --- | --- | --- |
| Output field | Server may return `null`. | Server commits not to return `null` when the field is requested. |
| Field argument | Client may omit or pass `null` unless other rules forbid it. | Client must supply a non-null value, unless a default value allows omitting it. |
| Input object field | Field may be omitted or passed as `null`. | Field must be provided and non-null if there is no default value. |

Input example:

```graphql
input CreateBookInput {
  title: String!
  subtitle: String
  authorId: ID!
  publishedAt: String
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
```

Clients must supply `title` and `authorId`. Clients can omit `subtitle`/`publishedAt` or pass null for those nullable fields. If a Non-Null input object field has a default value, the field may be omitted and GraphQL uses the default; an explicit null is still invalid.

### Omitted and explicit null are not the same

For a nullable input field, both requests below are valid yet carry different meanings:

```graphql
# Omit subtitle
mutation {
  createBook(input: { title: "GraphQL", authorId: "author-1" }) { id }
}

# Explicitly pass subtitle as null
mutation {
  createBook(input: { title: "GraphQL", subtitle: null, authorId: "author-1" }) { id }
}
```

In update APIs, omitted usually means keeping the existing value; explicit null may mean clearing the value. If the Java DTO simply uses `String subtitle`, both cases collapse to null after binding, losing information about what the client actually sent.

Spring for GraphQL provides `ArgumentValue<T>` to preserve the distinction between an omitted field and a field explicitly sent as null:

```java
import org.springframework.graphql.data.ArgumentValue;

public record UpdateBookInput(
        String id,
        ArgumentValue<String> subtitle) {
}
```

```java
@MutationMapping
public Book updateBook(@Argument("input") UpdateBookInput input) {
    if (input.subtitle().isOmitted()) {
        return bookService.keepSubtitle(input.id());
    }

    if (input.subtitle().value() == null) {
        return bookService.clearSubtitle(input.id());
    }

    return bookService.changeSubtitle(input.id(), input.subtitle().value());
}
```

To serialize optional inputs on the client, configure the GraphQL Jackson module matching the Jackson major version used by your transport (`GraphQlJacksonModule` or `GraphQlJackson2Module`) on the appropriate mapper/encoder. For server-side argument binding, use `ArgumentValue` when business logic needs to distinguish these two states.

## Is changing nullability backward-compatible?

You cannot judge a nullability change solely by whether `!` is added or removed. You must consider whether the field is in output or input, a list wrapper or item type, and how real clients send and read data.

### Output: nullable to Non-Null

Example:

```graphql
# Before
type User {
  displayName: String
}

# After
type User {
  displayName: String!
}
```

This narrows the set of values the server can return. For GraphQL clients, this is usually a compatible change because clients previously had to accept `String` or null; the server now commits to returning only a string. However, it is only safe when the resolver truly guarantees non-null in all valid cases.

Operational risks: legacy records may be null, services may fail to find a relation, authorization may mask the field, or downstream calls may fail. When any of those return null, GraphQL generates an error and null propagation can null out the parent object or list. Thus it is type-safe when backed by sufficient data evidence, not merely an SDL-only edit.

### Output: Non-Null to nullable

Example:

```graphql
# Before
type Order {
  discount: Float!
}

# After
type Order {
  discount: Float
}
```

This widens the set of values the server can return. Older clients may have generated non-nullable Java/Kotlin/TypeScript types and dereferenced the field directly. When the server starts returning null, clients can crash at runtime or require logic changes. This is typically a breaking change.

### Input: nullable to Non-Null

Example:

```graphql
# Before
input UpdateBookInput {
  authorId: ID
}

# After
input UpdateBookInput {
  authorId: ID!
}
```

Older clients may omit `authorId` or send an explicit null. After the change, operations can fail during validation/coercion before the resolver runs. This is a breaking change to the input contract.

### Input: Non-Null to nullable

Example:

```graphql
# Before
input CreateBookInput {
  authorId: ID!
}

# After
input CreateBookInput {
  authorId: ID
}
```

This relaxes the input constraint: older clients can keep sending values as before; newer clients can omit the field or send null. The change is usually backward-compatible, but the server must define behavior when the field is absent or null. If the business logic still requires an author, the validation/domain layer must return a deliberate error rather than leaving behavior ambiguous.

## Backward-compatibility matrix

| Change | Primary impact | Typical assessment |
| --- | --- | --- |
| Output `T` → `T!` | Server makes a stronger promise; clients see fewer nulls. | Usually compatible if resolver/data truly stay non-null. |
| Output `T!` → `T` | Clients may receive null previously disallowed by schema. | Breaking change. |
| Input `T` → `T!` | Clients must provide a non-null value. | Breaking change. |
| Input `T!` → `T` | Clients are allowed to omit or send null. | Usually compatible; new semantics must be defined. |
| Output list `[T]` → `[T!]` | Null elements become invalid; list can still be null. | Usually compatible if no null items occur. |
| Output list `[T]` → `[T]!` | List can no longer be null; items may still be null. | Usually compatible if resolver always returns a list. |
| Output `[T!]!` → `[T]` | Both list and items can become null again. | Breaking change for clients relying on old guarantees. |
| Input `[T]` → `[T!]` or `[T]!` | Further restricts values clients may send. | Breaking change if clients send null list/items. |
| Input `[T!]!` → `[T]` | Allows clients to omit the list or send null items. | Usually compatible; server must define handling for newly allowed values. |

This classification is at the GraphQL contract level. Platform schema checks may flag type changes and evaluate specific operations based on usage history. Even for output nullable to Non-Null, tools may still warn `FIELD_CHANGED_TYPE`; inspect resolvers, data, and operation impact before approving the change.

## Safely changing nullability with the expand-contract strategy

Do not change nullable to Non-Null solely because a database column is currently declared `NOT NULL`. APIs can have multiple data sources and resolvers; nulls can still arise from authorization, downstream failures, mapping, or historical records.

A workflow for changing output nullable to Non-Null:

1. **Measure current state:** find null records, how often resolvers return null, and related errors in production.
2. **Fix data:** backfill or clean up legacy data according to business rules.
3. **Fix resolvers/services:** ensure every execution path returns a valid value; handle missing-data cases explicitly.
4. **Test:** test legacy data, new data, missing relations, downstream errors, and authorization.
5. **Monitor:** deploy the updated resolver first and observe null/error rates over an adequate period.
6. **Tighten schema:** only change `T` to `T!` after having evidence that the new promise consistently holds.

For output Non-Null to nullable, if the contract must be relaxed, add a new nullable field, keep the old field for client migration, deprecate the old field when appropriate, and remove the old field in a planned breaking change. `@deprecated` does not alter nullability and does not make older clients automatically accept null.

For input nullable to Non-Null, you can add a new nullable input field first, update clients to supply the value, monitor usage, and then tighten it to Non-Null once all supported clients provide it. If waiting for migration is not feasible, create a new input type or mutation to represent the new contract.

## Using default values can avoid making inputs required

GraphQL allows a Non-Null argument or input field to have a default value. Clients can then omit the field and the server uses the default; explicit null is still rejected:

```graphql
type Query {
  books(first: Int! = 20): [Book!]!
}

input SearchBooksInput {
  first: Int! = 20
}
```

Do not confuse `Int! = 20` with `Int!` without a default. The first does not require the client to send the value; the second requires a value. The default value should preserve previous behavior so adding a new argument does not change results for existing operations.

Do not use artificial defaults if they mask data errors or create incorrect business behavior. For example, automatically replacing a null `authorId` with a default author could attach an order to the wrong entity.

## Designing Spring for GraphQL resolvers for nullability

SDL and Java return types should align. Example schema:

```graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  subtitle: String
}
```

The controller can return null for `book` when no record is found because `Query.book` is nullable. `title` must always have a value; `subtitle` is allowed to be absent:

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

If the schema changes to `book(id: ID!): Book!`, the resolver must not return null when not found. You can throw a business exception mapped to a GraphQL error, or design the field as nullable if "not found" is a normal API outcome. Do not catch an exception and return null for a Non-Null field, as that triggers an additional execution error and null propagation.

For relationship fields, clearly define what null means. For example, `Book.author: Author` can be nullable if a book may not yet have an assigned author; `Book.author: Author!` only makes sense when every served book has an author and resolution always succeeds per contract. If an author is deleted, hidden by permissions, or the author service temporarily fails, Non-Null can drop the entire `Book` object from the response.

### SDL Non-Null and Bean Validation

SDL `String!` and `@NotNull` on a DTO do not replace each other:

- SDL Non-Null is the GraphQL contract. GraphQL rejects missing or null inputs before calling the controller; for outputs, GraphQL checks the value returned by the `DataFetcher` and applies null propagation if violated.
- `@NotNull` is Java-layer validation after the argument has been bound. If SDL still declares `String`, clients can send null under the schema and only receive a validation error from the application afterward.
- `@NotBlank`, `@Size`, `@Positive`, and other constraints validate content rules that GraphQL Non-Null cannot express.

When changing nullability, update SDL, resolvers, and DTO/validation policies in sync. Do not assume adding `@NotNull` to a record has changed the GraphQL contract.

## Testing nullability changes with GraphQlTester

When changing a schema, test both valid values and contract-violation cases. For nullable outputs, test that null can be returned without generating an execution error:

```java
@Test
void nullableSubtitleCanBeNull() {
    graphQlTester.document("""
            query {
              book(id: "book-10") {
                id
                subtitle
              }
            }
            """)
            .execute()
            .path("book.subtitle")
            .valueIsNull()
            .path("book.id")
            .entity(String.class)
            .isEqualTo("book-10");
}
```

For Non-Null fields, deliberately set up a fixture where the resolver returns null to verify GraphQL produces an error and null propagates to the expected nullable parent:

```java
@Test
void nonNullAuthorFailureNullsBookParent() {
    graphQlTester.document("""
            query {
              book(id: "book-without-author") {
                id
                author {
                  name
                }
              }
            }
            """)
            .execute()
            .errors()
            .expect(error -> error.getPath().contains("author"))
            .verify()
            .path("book")
            .valueIsNull();
}
```

The test assumes `Book.author` is `Author!` and `Query.book` is nullable `Book`. If the parent is also Non-Null, null propagates further; adjust assertions to match your schema structure.

For Non-Null inputs, test both omitted and explicit null cases:

```java
@Test
void requiredAuthorIdCannotBeOmitted() {
    graphQlTester.document("""
            mutation {
              createBook(input: { title: "Spring GraphQL" }) {
                id
              }
            }
            """)
            .execute()
            .errors()
            .expect(error -> error.getMessage().contains("authorId"))
            .verify();
}
```

Explicit null is also rejected:

```java
@Test
void requiredAuthorIdCannotBeNull() {
    graphQlTester.document("""
            mutation CreateBook($authorId: ID!) {
              createBook(input: { title: "Spring GraphQL", authorId: $authorId }) {
                id
              }
            }
            """)
            .variable("authorId", null)
            .execute()
            .errors()
            .expect(error -> error.getMessage().contains("authorId"))
            .verify();
}
```

When running schema checks in CI, compare the current schema with the published schema and analyze real operations. With Apollo GraphOS, build checks verify valid schema composition; operations checks compare observed operations to detect potentially impacted clients. Schema checks support decision-making, but do not replace resolver tests and production data checks.

## Checklist before changing `!`

- Determine whether this is an output field, field argument, or input object field.
- For lists, determine whether `!` applies to the list wrapper or the item type.
- Define the semantics of null: does not exist, not yet available, unauthorized, or system error.
- Check whether resolvers, services, databases, downstreams, and authorization can return null.
- Check legacy data and migration/backfill needs.
- Determine how client generated types may be affected.
- Distinguish omitted vs. explicit null for update/patch inputs.
- Check default values; Non-Null with a default can still be omitted.
- Write tests for null, empty string, empty list, missing input, and explicit null.
- Verify error paths and null propagation for Non-Null fields.
- Run schema diffs/operation checks and track usage before removing old contracts.
- Deploy resolver/data behavior in sync with the schema to avoid mismatches between schema and runtime.

## Key takeaways

GraphQL is nullable by default. `!` is a strong server commitment for outputs and a stricter requirement for inputs. For lists, `[T]`, `[T]!`, `[T!]`, and `[T!]!` differ in nullability of the list and each item; an empty list remains valid in every form.

Output nullable to Non-Null is usually compatible if the resolver genuinely always has a value; output Non-Null to nullable is breaking because clients can receive null. Input nullable to Non-Null is breaking because clients may omit or send null; input Non-Null to nullable is usually a relaxation, though new behavior must be defined. When Non-Null is violated, GraphQL generates an error and null propagates up to the nearest nullable parent. Measure data, update resolvers, test null propagation, and migrate clients via the expand-contract strategy before altering the contract.

## References

- [GraphQL Specification — Type System: Non-Null and List](https://spec.graphql.org/September2026/#sec-Non-Null)
- [GraphQL Specification — Handling Execution Errors](https://spec.graphql.org/September2026/#sec-Handling-Field-Errors)
- [GraphQL.org — Schema and Type Modifiers](https://graphql.org/learn/schema/)
- [GraphQL.org — Schema Design: Nullability](https://graphql.org/learn/schema-design/)
- [GraphQL.org — Schema Change Management](https://graphql.org/learn/governance-versioning/)
- [Apollo GraphOS — Schema Checks](https://www.apollographql.com/docs/graphos/platform/schema-management/checks)
