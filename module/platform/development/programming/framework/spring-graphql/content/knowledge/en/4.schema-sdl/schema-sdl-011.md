# Naming types and fields in a GraphQL Schema

## Objectives

After this lesson, you will be able to:

- Apply GraphQL's valid naming syntax rules.
- Distinguish naming conventions for object types, interfaces, unions, scalars, enums, and input types.
- Name fields, arguments, and root fields so they accurately express business semantics.
- Use consistent casing, singular/plural forms, and abbreviations.
- Write schema descriptions so clients understand the meaning of types and fields.
- Spot vague names, names tied to implementation details, and introspection-reserved names.
- Rename schema elements safely to minimize impact on existing clients.

## 1. Why naming matters in GraphQL

In GraphQL, the schema is the contract clients use directly. Clients write operations using the type, field, argument, and enum value names published by the server. IDEs, introspection tools, and code generators also rely on these names for autocomplete, validation, and code generation.

For example, both schemas below can return information about a book:

~~~graphql
type Query {
    getBookById(bookID: ID!): Book
}
~~~

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

The second schema is concise and accurately models the resource clients are querying. Client operations become easier to read too:

~~~graphql
query FindBook {
    book(id: "book-42") {
        id
        title
    }
}
~~~

Good naming helps:

- Clients understand what data a field returns without reading the implementation.
- Schemas stay discoverable in GraphiQL, GraphQL IDEs, and introspection.
- Types and fields remain consistent across multiple development teams.
- Auto-generated client code stay readable and unambiguous.
- API evolution proceed without accumulating multiple near-identical names.

Names in GraphQL are part of the public API. Renaming a field, argument, type, or enum value can break client operations. Therefore, naming should be decided upfront during schema design.

## 2. Syntax rules for a GraphQL name

GraphQL uses a uniform syntax rule for names (`Name`). A valid name:

- Starts with an ASCII letter or an underscore.
- Subsequent characters may be ASCII letters, digits, or underscores.
- Is case-sensitive.
- Contains no hyphens, spaces, or periods.

General pattern:

~~~text
[_A-Za-z][_0-9A-Za-z]*
~~~

Examples:

| Name | Valid? | Explanation |
| --- | --- | --- |
| `Book` | Yes | Starts with a letter |
| `bookDetail` | Yes | camelCase letters |
| `book_2` | Yes | Digit after the first character |
| `_internalCode` | Syntactically valid | Leading underscore is allowed |
| `2Book` | No | Starts with a digit |
| `book-title` | No | Contains a hyphen |
| `book.title` | No | Contains a period |
| `book title` | No | Contains whitespace |

GraphQL is case-sensitive. `Book`, `book`, and `BOOK` are three distinct names. Never vary capitalization across references.

Names starting with two underscores, such as `__typename`, are reserved for GraphQL's introspection system. Do not name application types, fields, or schema elements with the `__` prefix. Clients can use `__typename` to inspect the concrete type of a value at runtime.

Note: although the syntax permits leading underscores, not every name starting with an underscore is a good choice. Reserve internal-looking conventions only when genuinely needed and stay clear of the introspection namespace.

## 3. Capitalization conventions

GraphQL does not mandate a specific casing style for each kind of element. However, the GraphQL community follows widespread conventions that let readers identify the kind of element at a glance.

| Element | Common convention | Example |
| --- | --- | --- |
| Object type | PascalCase | `Book`, `Author` |
| Interface | PascalCase | `Node`, `Publishable` |
| Union | PascalCase | `SearchResult` |
| Custom scalar | PascalCase | `DateTime`, `EmailAddress` |
| Enum type | PascalCase | `BookStatus` |
| Enum value | UPPER_SNAKE_CASE | `IN_STOCK`, `OUT_OF_STOCK` |
| Field | lowerCamelCase | `title`, `publishedAt` |
| Argument | lowerCamelCase | `authorId`, `pageSize` |
| Input object | PascalCase, usually ending in Input | `CreateBookInput` |
| Mutation payload | PascalCase, usually ending in Payload | `CreateBookPayload` |
| Client operation name | PascalCase | `FindBookDetail` |

These conventions do not change how GraphQL executes, but they create a shared vocabulary across the schema.

### 3.1. PascalCase for type names

Type names should be nouns or domain concepts:

~~~graphql
scalar Money

type Book {
    id: ID!
    title: String!
}

type Author {
    id: ID!
    name: String!
}
~~~

`Book` and `Author` represent two concepts clients readily recognize. Do not name types after database tables or persistence classes if those names do not reflect the API contract.

### 3.2. lowerCamelCase for fields and arguments

Fields and arguments start with a lowercase letter, with subsequent words capitalized:

~~~graphql
type Book {
    id: ID!
    publishedAt: DateTime
    coverImageUrl: String
}

type Query {
    book(authorId: ID!): Book
}
~~~

Use `authorId`, `publishedAt`, and `coverImageUrl` consistently instead of mixing `authorID`, `published_at`, or `cover_image_url`.

### 3.3. UPPER_SNAKE_CASE for enum values

Enum values are typically uppercase with words separated by underscores:

~~~graphql
enum OrderStatus {
    PENDING_PAYMENT
    PAID
    READY_TO_SHIP
    SHIPPED
    CANCELLED
}
~~~

The enum type name still uses PascalCase. Only the values inside the enum use UPPER_SNAKE_CASE.

## 4. Naming different kinds of types

Type names should reflect concepts clients work with, not how data is stored or how the server is implemented.

### 4.1. Object types: singular nouns

Object types typically use singular nouns because a value of that type represents a single entity:

~~~graphql
type Book {
    id: ID!
    title: String!
}

type Author {
    id: ID!
    name: String!
}
~~~

Use `Book` rather than `Books` for the object type. When a field returns a list, the field name itself is usually plural:

~~~graphql
type Query {
    book(id: ID!): Book
    books: [Book!]!
}
~~~

This rule lets readers distinguish a single object from a collection of objects straight from the field name.

### 4.2. Interfaces: naming shared contracts

An interface represents a set of fields shared across multiple object types. Interface names should describe a shared concept or capability:

~~~graphql
scalar DateTime

interface Node {
    id: ID!
}

interface Publishable {
    publishedAt: DateTime
}

type Book implements Node & Publishable {
    id: ID!
    title: String!
    publishedAt: DateTime
}

type Article implements Node & Publishable {
    id: ID!
    headline: String!
    publishedAt: DateTime
}
~~~

`Node` describes an identifiable object; `Publishable` describes the capability of being published. Interface names should not be tied to a specific Java class or repository technical detail.

Create an interface only when types genuinely share a meaningful contract. Do not create an interface merely to group fields that happen to share names with different semantics.

### 4.3. Unions: naming result groups

A union represents a value that can belong to one of several object types. Its name should describe the result group or shared role:

~~~graphql
union CatalogSearchResult = Book | Author | Article

type Query {
    searchCatalog(keyword: String!): [CatalogSearchResult!]!
}
~~~

`CatalogSearchResult` tells clients this is a search result from the catalog. A name like `BookOrAuthorOrArticle` becomes unwieldy and hard to extend when a new type is added.

### 4.4. Custom scalars: stating data meaning clearly

Custom scalars should have names describing the format or meaning of the value:

~~~graphql
scalar DateTime
scalar EmailAddress
scalar ISBN
scalar Money
~~~

Do not create a scalar for every Java type. For instance, if an identifier is just a string with no special conversion rules, `String` or `ID` may suffice. Use custom scalars only when the application has explicit parsing, validation, and serialization conventions.

Scalar names should align with the data contract. `DateTime` suggests a timestamp with defined formatting rules; `EmailAddress` suggests an email string validated under dedicated rules.

### 4.5. Input objects: adding the Input suffix

Input objects represent data sent by clients. The `Input` suffix distinguishes them from output objects:

~~~graphql
input CreateBookInput {
    title: String!
    authorId: ID!
    publishedYear: Int
}

input UpdateBookInput {
    id: ID!
    title: String
    publishedYear: Int
}
~~~

`CreateBookInput` and `UpdateBookInput` clearly express the purpose of each input. Do not name both `BookRequest` or `BookData` if that name fails to indicate which operation is being performed.

### 4.6. Payload types: describing mutation results

When a mutation returns multiple pieces of information about the operation's outcome, you can use a payload type:

~~~graphql
type CreateBookPayload {
    book: Book
    created: Boolean!
}

type Mutation {
    createBook(input: CreateBookInput!): CreateBookPayload!
}
~~~

The `Payload` suffix helps clients recognize this as the result type of an action. For a simple mutation returning only a single object, you can return that object directly; do not invent a payload type if it adds no extra value.

## 5. Naming fields by business semantics

Fields are what clients see most often. A field name should answer: "What is this value?" or "What does this action do?"

Example:

~~~graphql
type Book {
    id: ID!
    title: String!
    author: Author!
    publishedAt: DateTime
    coverImageUrl: String
}
~~~

The fields `title`, `author`, `publishedAt`, and `coverImageUrl` describe domain data. They do not reveal whether the server reads from a database, cache, or external API.

Avoid names tied to implementation details:

~~~graphql
type Book {
    redisBookValue: String
    bookEntity: String
    getTitleFromDatabase: String
}
~~~

If the server later migrates from Redis to another database, the field name becomes misleading even though the data contract has not changed. Schema names should remain stable around business semantics.

### 5.1. Avoid overly generic names

Names like `data`, `value`, `result`, `info`, or `item` may be valid syntax, yet they usually lack sufficient context:

~~~graphql
type Book {
    data: String
    info: String
    value: String
}
~~~

Schema consumers cannot tell what data these fields represent. Use specific names:

~~~graphql
type Book {
    summary: String
    publisherName: String
    retailPrice: Money
}
~~~

Generic names are only suitable when the surrounding type or structure already supplies clear context and the name genuinely represents a shared concept.

### 5.2. Use nouns for data, verbs for actions

Read fields typically use nouns or noun phrases:

- `book`
- `author`
- `publicationDate`
- `orderStatus`

Action fields on the root mutation typically use clear verbs:

- `createBook`
- `updateBook`
- `publishBook`
- `cancelOrder`

This naming style distinguishes data queries from state-modifying actions.

### 5.3. Do not repeat the type name in every field

Inside the `Book` object type, fields such as `bookTitle`, `bookAuthor`, and `bookPublishedAt` repeat information already conveyed by the type name.

You can write them more concisely:

~~~graphql
type Book {
    title: String!
    author: Author!
    publishedAt: DateTime
}
~~~

Field names should have sufficient context within their enclosing type without repeating the type name unless doing so adds clarity.

## 6. Naming root Query, Mutation, and Subscription fields

The three root operation types serve different purposes. Field names should reflect the behavior clients perform.

### 6.1. Query: resource names or search actions

When querying a single object, use a singular noun:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

For a list, use a plural noun:

~~~graphql
type Query {
    books: [Book!]!
}
~~~

When an operation has explicit search semantics, starting with a search verb can be appropriate:

~~~graphql
type Query {
    searchBooks(keyword: String!): [Book!]!
}
~~~

There is no need to prefix every Query field with `get`. The `book` field already clearly shows the client is requesting a book. Use `get` only when it is part of an intentional domain vocabulary applied consistently.

### 6.2. Mutation: action verb + target object

Mutations modify data, so names typically start with a verb:

~~~graphql
type Mutation {
    createBook(input: CreateBookInput!): CreateBookPayload!
    updateBook(input: UpdateBookInput!): Book!
    publishBook(id: ID!): Book!
    archiveBook(id: ID!): Book!
}
~~~

Mutation names should describe specific business actions. `saveBook` can be too vague because it does not clarify whether it creates, updates, or saves a draft. `manageBook` likewise does not indicate which state will change.

When an action follows domain-specific rules, choose verbs matching the business domain, such as `approveOrder`, `rejectOrder`, or `shipOrder`.

### 6.3. Subscription: naming events

Subscriptions typically describe the event a client wants to observe:

~~~graphql
type Subscription {
    bookAdded: Book!
    bookPublished: Book!
    orderStatusChanged(orderId: ID!): Order!
}
~~~

Names such as `bookAdded`, `bookPublished`, and `orderStatusChanged` tell clients which event or change they are subscribing to. Choose a consistent naming style across subscriptions in the same domain.

If a subscription emits an object representing the event rather than the domain entity itself, name the type after the event:

~~~graphql
type BookStatusChangedEvent {
    bookId: ID!
    previousStatus: BookStatus!
    currentStatus: BookStatus!
    occurredAt: DateTime!
}

type Subscription {
    bookStatusChanged(bookId: ID!): BookStatusChangedEvent!
}
~~~

## 7. Naming arguments clearly and consistently

Arguments are inputs to each field. Argument names also use lowerCamelCase and should describe the passed value.

~~~graphql
type Query {
    book(id: ID!): Book
    booksByAuthor(authorId: ID!): [Book!]!
}
~~~

`id` is a standard name for the identifier of the queried object itself. `authorId` clarifies that the identifier belongs to the author. When a field accepts multiple identifiers, explicit names prevent confusion.

### 7.1. Use consistent names for filtering, sorting, and pagination

If multiple Queries support filtering and sorting, standardize argument names:

~~~graphql
input BookFilter {
    titleContains: String
    authorId: ID
    status: BookStatus
}

enum SortDirection {
    ASC
    DESC
}

input BookSort {
    field: BookSortField!
    direction: SortDirection! = ASC
}

enum BookSortField {
    TITLE
    PUBLISHED_AT
}

type Query {
    books(
        filter: BookFilter
        sort: BookSort
        page: Int = 0
        size: Int = 20
    ): [Book!]!
}
~~~

Names like `filter`, `sort`, `page`, and `size` should be used consistently across fields following the same convention. If the API uses cursor pagination, choose `first`/`after` or `last`/`before` consistently.

Avoid using `limit` on one Query, `pageSize` on another, and `count` on a third when they all mean the same thing with no domain reason to differ.

### 7.2. Avoid cryptic abbreviations

Argument names like `authId`, `pubDt`, or `usrCd` are short, yet force clients to look up documentation. Prefer `authorId`, `publishedAt`, and `userCode` if those are the domain terms.

Common abbreviations such as `id`, `url`, or `isbn` can be kept as-is when both the development team and API consumers clearly understand them. The rule is to pick one spelling and use it consistently without inventing multiple capitalization variants.

## 8. Naming Booleans, statuses, and timestamps

Field names should hint at the kind of value they return.

### 8.1. Booleans: use question-style prefixes

Booleans often read naturally as yes/no questions:

~~~graphql
type Book {
    isPublished: Boolean!
    hasCoverImage: Boolean!
    canBeBorrowed: Boolean!
}
~~~

Common prefixes:

- `is`: state, e.g., `isPublished`.
- `has`: existence or possession, e.g., `hasCoverImage`.
- `can`: capability or permission, e.g., `canBeBorrowed`.

Avoid naming a Boolean `published` if clients might mistake it for a publication timestamp. If the field returns a date/time, use `publishedAt`.

### 8.2. Distinguishing Booleans from status enums

If an object has multiple states, a Boolean may not be expressive enough:

~~~graphql
type Order {
    isCompleted: Boolean!
}
~~~

If an order goes through pending payment, paid, shipping, and delivered states, an enum expresses this far more clearly:

~~~graphql
enum OrderStatus {
    PENDING_PAYMENT
    PAID
    SHIPPING
    DELIVERED
    CANCELLED
}

type Order {
    status: OrderStatus!
}
~~~

The name `status` has clear context inside `Order`. If a type holds multiple distinct kinds of status, name them more specifically, such as `paymentStatus` and `shippingStatus`.

### 8.3. Timestamps and calendar dates

Use clear suffixes for time fields:

- `createdAt`: creation timestamp.
- `updatedAt`: most recent update timestamp.
- `publishedAt`: publication timestamp.
- `expiresAt`: expiration timestamp.
- `dueDate`: due date when representing a calendar date only.

Distinguish calendar dates from exact timestamps. `dueDate` and `dueAt` should not be used interchangeably if their data contracts differ.

## 9. Naming enums and enum values

Enum types use PascalCase; enum values use UPPER_SNAKE_CASE:

~~~graphql
enum PaymentStatus {
    PENDING
    AUTHORIZED
    CAPTURED
    REFUNDED
    FAILED
}
~~~

Enum values should represent states or choices with clear meaning in the domain.

Avoid overly generic or position-dependent names:

~~~graphql
enum Status {
    VALUE_1
    VALUE_2
    OTHER
}
~~~

`VALUE_1` and `VALUE_2` convey no business meaning. If the status represents payment, name the enum and values after payment statuses.

For a catch-all value, use `OTHER` only when the domain genuinely has an "other" concept that clients can handle. Do not use `UNKNOWN` as a placeholder for an unspecified value if the server can represent an unknown state via nullability or a dedicated meaningful state.

Enum value names are also part of the contract. When clients pass an enum value in variables, renaming or removing an old value can make requests invalid.

## 10. Documenting schemas with descriptions

Good names are essential, yet some fields still need explicit explanations of scope and rules. GraphQL supports descriptions using strings placed before type, field, argument, or enum value definitions.

~~~graphql
"""
A book available in the catalog.
"""
type Book {
    """Stable identifier of this book."""
    id: ID!

    """The title displayed to readers."""
    title: String!

    """
    The date when the book was first published.
    The value is null when the publication date is unknown.
    """
    publishedAt: DateTime
}
~~~

Descriptions allow IDEs and introspection tools to display documentation right alongside field names. They are the right place to explain:

- Units of measurement or value formats.
- Meaning of nullable values.
- Filtering, sorting, and pagination rules.
- Business preconditions for mutations.
- Access scope or usage limits clients need to know.

Do not use descriptions to compensate for an overly vague name. Pick a clear name first, then use descriptions for details that cannot fit concisely into the name.

Comments starting with `#` in SDL are notes for source-file readers. If you want documentation to appear in introspection and GraphQL tools, use description strings.

## 11. Example schema with consistent naming

The following example combines the conventions covered above in a book catalog domain:

~~~graphql
scalar DateTime

"""
A book in the catalog.
"""
type Book {
    """Stable identifier of the book."""
    id: ID!

    """Title displayed to readers."""
    title: String!

    """Author of the book."""
    author: Author!

    """Publication date, if known."""
    publishedAt: DateTime

    """Current status in the book's lifecycle."""
    status: BookStatus!
}

"""
A person who writes books.
"""
type Author {
    id: ID!
    fullName: String!
    books: [Book!]!
}

enum BookStatus {
    DRAFT
    PUBLISHED
    ARCHIVED
}

input BookFilter {
    titleContains: String
    authorId: ID
    status: BookStatus
}

enum BookSortField {
    TITLE
    PUBLISHED_AT
}

enum SortDirection {
    ASC
    DESC
}

input BookSort {
    field: BookSortField!
    direction: SortDirection! = ASC
}

input CreateBookInput {
    title: String!
    authorId: ID!
    publishedAt: DateTime
}

type CreateBookPayload {
    book: Book!
}

type Query {
    book(id: ID!): Book
    books(
        filter: BookFilter
        sort: BookSort
        page: Int = 0
        size: Int = 20
    ): [Book!]!
}

type Mutation {
    createBook(input: CreateBookInput!): CreateBookPayload!
    publishBook(id: ID!): Book!
}

type Subscription {
    bookPublished: Book!
}
~~~

Notice the conventions applied:

- Types use PascalCase and singular nouns.
- Fields use lowerCamelCase.
- List fields use plural nouns.
- Enum values use UPPER_SNAKE_CASE.
- Inputs and payloads carry suffixes indicating their role.
- Query fields describe the resources to read.
- Mutation fields start with action verbs.
- Subscription fields describe events.
- Descriptions explain the meaning of key fields.

This example schema focuses on naming. In a real implementation, ensure resolvers exist for business fields and scalars are configured for all declared custom scalars.

## 12. Naming patterns to avoid

| Naming pattern | Problem | How to improve |
| --- | --- | --- |
| `getBookById` | Redundant `get` prefix on Query | `book(id: ID!)` |
| `Books` as an object type | Plural name gets confused with a list | `Book` |
| `book_title` | Mixes snake_case with camelCase conventions | `title` |
| `bookTitle` inside type `Book` | Repeats the type name | `title` |
| `usrId` | Cryptic abbreviation | `userId` |
| `data` or `value` | Conveys no semantics | Specific domain name |
| `saveBook` | Unclear whether it creates or updates | `createBook` or `updateBook` |
| `Status` for every status | Unclear which entity the status belongs to | `BookStatus`, `OrderStatus` |
| `BookDTO` | Exposes server-side class organization | `Book` |
| `__book` | Uses prefix reserved for introspection | Choose a name not starting with `__` |

A schema with many near-synonymous names also creates confusion:

~~~graphql
type Query {
    book(id: ID!): Book
    getBook(id: ID!): Book
    findBook(id: ID!): Book
    fetchBook(id: ID!): Book
}
~~~

These four fields might execute the exact same query. Clients will not know which one to pick. Standardize on one representative name per concept, and create separate fields only when they have genuinely distinct semantics or behavior.

## 13. Renaming schema elements and compatibility

Because clients reference schema names directly, renaming is a potentially breaking change.

For example, if you currently have:

~~~graphql
type Book {
    name: String!
}
~~~

and want to rename it to `title`, existing clients might still be sending:

~~~graphql
query {
    book(id: "book-42") {
        name
    }
}
~~~

Deleting or renaming `name` immediately will invalidate existing operations.

A safer transition is to add the new field and mark the old field deprecated:

~~~graphql
type Book {
    title: String!

    name: String @deprecated(reason: "Use title instead")
}
~~~

Then:

1. Announce the new field to client teams.
2. Update clients to use the new field.
3. Monitor usage of the old field if your system has appropriate observability.
4. Remove the old field only after confirming no clients still depend on it and the release process allows it.

Apply the same process when renaming arguments, types, or enum values. Descriptions and deprecation reasons should state the new name clearly so schema consumers know how to migrate.

Not every rename can rely on server-side aliases to preserve compatibility. An alias in an operation is a response key chosen by the client; it does not compensate for an old field disappearing from the schema.

## 14. Checklist before publishing a schema

Before releasing a schema into use, review:

- Do names obey GraphQL syntax and avoid the reserved `__` prefix?
- Do types use PascalCase and accurately model domain concepts?
- Do object types use singular nouns and list fields use plural names?
- Do fields and arguments use lowerCamelCase consistently?
- Do enum types and enum values follow the conventions?
- Do input and payload names clearly indicate their role?
- Do Boolean names clearly read as true/false questions?
- Do time-related names distinguish calendar dates from exact timestamps?
- Are any field names overly generic, cryptically abbreviated, or leaking implementation details?
- Do Query, Mutation, and Subscription fields clearly express their behavior?
- Are old fields or enum values deprecated with clear migration reasons?
- Do descriptions explain rules that names alone cannot fully convey?

## 15. Summary

Naming in GraphQL is part of the API contract. Type names should express domain concepts; fields and arguments need clear semantics; enum values should be consistent; inputs and payloads should use suffixes that help readers identify their roles. PascalCase, lowerCamelCase, and UPPER_SNAKE_CASE conventions yield readable, discoverable schemas.

When designing names, prioritize the meaning clients need to understand and avoid coupling the schema to database or implementation details. Add descriptions for important rules and use deprecation when changing published names. A schema with clear naming helps clients write accurate operations, helps teams communicate consistently, and lets the API evolve under control.
