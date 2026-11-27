# Schema and Operations in GraphQL

## Objectives

After this lesson, you will be able to:

- Explain what a GraphQL schema describes and how operations use the schema.
- Read and write schemas using GraphQL Schema Definition Language (SDL).
- Declare object types, scalars, enums, input types, root operation types, lists, and non-null fields.
- Write Queries, Mutations, and Subscriptions with arguments, variables, aliases, fragments, and directives.
- Read request/response structures, and recognize validation errors and execution errors.
- Know where to place schemas and how to connect operations to handlers in a Spring for GraphQL application.

## 1. Schema and operations form the API contract

A GraphQL API has two complementary parts:

- **Schema** describes the data types, fields, and operations that the server exposes. This is the contract that clients can discover and validate against.
- **Operation** is the specific request sent by the client, indicating whether it wants to read data, modify data, or subscribe to an event stream, along with the fields to fetch.

For example, the schema may expose the field **book(id: ID!): Book** on the **Query** root type. The client can send a query fetching **id**, **title**, and **author.name** for a book. The client does not need to receive every property of **Book**; it selects the exact fields it needs.

General processing flow:

1. The client sends an operation along with variables (if any).
2. The GraphQL server parses and validates the operation against the schema.
3. If the operation is valid, the server executes the requested fields and invokes the corresponding data handlers.
4. The server returns data matching the client's selection set structure, along with error details if any occurred.

The schema is the API contract, not a database description. A field can be computed, aggregated from multiple sources, or fetched from another service; the schema only specifies the shape and data types that clients are allowed to request.

## 2. Declaring a schema with SDL

SDL is GraphQL's type declaration syntax. A schema is typically organized into type definitions. Each type has a name and fields; each field has a return type and may take arguments.

Simple example:

~~~graphql
type Book {
    id: ID!
    title: String!
    publishedYear: Int
}
~~~

**Book** is an object type. Clients can request the **id**, **title**, and **publishedYear** fields when querying a value of type **Book**.

### 2.1. Built-in scalars

GraphQL has five built-in scalars:

| Scalar | Meaning |
| --- | --- |
| **Int** | Signed 32-bit integer |
| **Float** | Floating-point number |
| **String** | Character string |
| **Boolean** | True or false value |
| **ID** | Unique identifier for an object |

**ID** is commonly used for identifier keys and is serialized as a string in responses. It does not have to be a database primary key; the server can use a UUID, business code, or another identifier.

When domain-specific data types like **DateTime** are needed, the schema can declare a custom scalar:

~~~graphql
scalar DateTime

type Event {
    id: ID!
    startsAt: DateTime!
}
~~~

Declaring **scalar DateTime** only creates the type name in the schema. The application still has to provide input parsing and output serialization for that scalar at runtime. Therefore, custom scalars should only be created when there is a clear representation and conversion convention.

### 2.2. Object types and relationships between types

An object type describes an object from which clients can select fields. A field can return a scalar, an enum, another object type, or a list of values.

~~~graphql
type Author {
    id: ID!
    name: String!
    books: [Book!]!
}

type Book {
    id: ID!
    title: String!
    author: Author!
}
~~~

**Book.author** returns an **Author**, while **Author.books** returns a list of **Book**. Two types can reference each other; GraphQL lets you describe such relationships without embedding all data inline in the schema.

Declaring a relationship does not mean the server automatically knows how to load the data. At execution time, the server must have a way to obtain the value for each field, such as from an object property, repository, or service.

### 2.3. Enums to restrict the value set

Use an enum when a field only accepts a finite set of known values:

~~~graphql
enum BookStatus {
    DRAFT
    PUBLISHED
    ARCHIVED
}

type Book {
    id: ID!
    title: String!
    status: BookStatus!
}
~~~

Enums let clients know valid values upfront and avoid guessing arbitrary strings. Enum values are commonly written in uppercase by convention.

### 2.4. Lists and nullability

GraphQL uses square brackets to declare lists and **!** to mark a value as non-nullable. These two rules can be combined:

| Declaration | Meaning |
| --- | --- |
| **Book** | A **Book** or **null** |
| **Book!** | A **Book** is required |
| **[Book]** | The list can be **null**; each element can also be **null** |
| **[Book!]** | The list can be **null**; each element cannot be **null** |
| **[Book]!** | The list cannot be **null**; each element can be **null** |
| **[Book!]!** | Both the list and every element cannot be **null** |

Example:

~~~graphql
type Query {
    book(id: ID!): Book
    books: [Book!]!
}
~~~

**book** can return **null**, which fits the case where the book is not found. **books** must return a list; the list can be empty, but it cannot be **null**, and no element can be **null**.

Choosing nullability is an API contract decision. If real-world data can be absent, do not add **!** just to make the schema look stricter. When a field declared non-null returns **null** at execution time, GraphQL produces an error and bubbles **null** up to the nearest nullable parent field. This can cause a larger portion of the response to become **null**.

### 2.5. Input types for data sent by clients

Object types describe returned data. For input data, GraphQL uses **input**:

~~~graphql
input CreateBookInput {
    title: String!
    authorId: ID!
    publishedYear: Int
}
~~~

An input object can contain scalars, enums, and other input objects, along with lists of those valid types. It cannot directly use an output object type like **Book** or **Author**.

A mutation can accept an input object as an argument:

~~~graphql
type Mutation {
    createBook(input: CreateBookInput!): Book!
}
~~~

This groups related properties into a clear structure. As business requirements add input fields, the schema can extend the input object without turning the mutation into a long list of arguments.

## 3. Root operation types

GraphQL defines three types of operations. Each type starts from a corresponding root type.

### 3.1. Query — reading data

**Query** is the required root type of a schema. Fields on **Query** are the entry points for data-reading requests.

~~~graphql
type Query {
    book(id: ID!): Book
    books(limit: Int = 20): [Book!]!
}
~~~

In this example:

- **book** accepts a required argument **id** and returns a **Book** or **null**.
- **books** accepts **limit**, with a default value of **20**, and returns a non-null list.

Queries should be designed to read data and produce no business side effects. GraphQL does not automatically prevent a Query resolver from writing to a database; this is a convention the API must follow so clients can predict behavior.

### 3.2. Mutation — modifying data

**Mutation** is the root type for creating, updating, or deleting data.

~~~graphql
type Mutation {
    createBook(input: CreateBookInput!): Book!
}
~~~

A mutation typically accepts an input describing the change and returns the data needed after the change. Returning an object instead of just a Boolean allows the client to immediately select the fields needed to update the UI.

Top-level fields in a single mutation operation are executed sequentially in the order they appear. Therefore, if an operation contains multiple dependent mutation fields, execution order matters. Still, each mutation should represent a clear business action; avoid bundling unrelated changes into a single request.

### 3.3. Subscription — receiving events over time

**Subscription** describes an event stream that clients subscribe to.

~~~graphql
type Subscription {
    bookAdded: Book!
}
~~~

This example exposes the **bookAdded** field. When a new book event occurs, the server can push a result to subscribed clients. Subscriptions are suitable for status notifications, live updates, or business events that need to be pushed to clients.

Subscriptions have a stream-based lifecycle, unlike the typical request/response of Query and Mutation. The server needs to configure a streaming-capable transport, such as WebSocket or RSocket depending on the application architecture. A subscription operation selects only one root field to identify the event stream to follow.

### 3.4. Declaring the schema root

A complete schema for the book example can be written as follows:

~~~graphql
type Author {
    id: ID!
    name: String!
    books: [Book!]!
}

enum BookStatus {
    DRAFT
    PUBLISHED
    ARCHIVED
}

type Book {
    id: ID!
    title: String!
    status: BookStatus!
    publishedYear: Int
    author: Author!
}

input CreateBookInput {
    title: String!
    authorId: ID!
    publishedYear: Int
}

type Query {
    book(id: ID!): Book
    books(limit: Int = 20): [Book!]!
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
}

type Subscription {
    bookAdded: Book!
}

schema {
    query: Query
    mutation: Mutation
    subscription: Subscription
}
~~~

In SDL, the **schema** declaration can be omitted when using the conventional root names **Query**, **Mutation**, and **Subscription**. Writing it explicitly as above is useful when you want to clearly show entry points or when the schema uses different root names.

Not every application needs all three root types. Query is required; Mutation and Subscription only need to be declared when the API provides those capabilities.

## 4. Writing operations from a schema

An operation is an executable document consisting of operation definitions and optionally fragments. Clients may only select fields present in the schema, pass arguments of the right types, and select the required subfields.

### 4.1. Selection set

A basic query:

~~~graphql
query {
    book(id: "book-101") {
        id
        title
        author {
            id
            name
        }
    }
}
~~~

The part inside the curly braces after **book** is the selection set. The client selects the **id**, **title**, and **author** fields; because **author** is an object type, the client further selects **id** and **name** inside it.

Important rules:

- For fields returning a scalar or enum, do not write a nested selection set.
- For fields returning an object or list of objects, subfields must be selected.
- Requested fields must exist on the corresponding type in the schema.
- Clients can select fewer or more fields as needed; the server returns the exact selected structure.

The following example is invalid because **title** is a scalar:

~~~graphql
query {
    book(id: "book-101") {
        title {
            length
        }
    }
}
~~~

Similarly, requesting only **book** without a selection set is also invalid because **book** returns a **Book** object.

### 4.2. Naming operations

You should name operations to make reading logs, tracing errors, and monitoring requests easier:

~~~graphql
query GetBookDetail {
    book(id: "book-101") {
        id
        title
    }
}
~~~

The operation name is optional when the document contains only one operation. If the document contains multiple operations, the request must specify which operation to run via **operationName**.

~~~graphql
query GetBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}

query GetBooks($limit: Int) {
    books(limit: $limit) {
        id
        title
    }
}
~~~

When sending the document above, the client must pass **operationName** as **GetBook** or **GetBooks** so the server selects the right operation.

### 4.3. Arguments and variables

Arguments are values passed into fields. Literal values can be written directly in the operation, but for data that changes per request, variables should be used.

~~~graphql
query GetBook($id: ID!, $withAuthor: Boolean! = true) {
    book(id: $id) {
        id
        title
        author @include(if: $withAuthor) {
            id
            name
        }
    }
}
~~~

Variables are declared at the start of the operation. **$id: ID!** means the client must supply a non-null ID value. **$withAuthor** has a default value of **true**, so the client can omit this variable if it wants to use the default.

Variables are sent separately, typically as JSON:

~~~json
{
    "id": "book-101",
    "withAuthor": true
}
~~~

Separating variables from the query string has several benefits:

- Avoids concatenating input data directly into GraphQL query text.
- Enables the server to validate data types against the schema.
- Makes it easy to reuse the same operation across many datasets.
- Keeps operation logging and caching more consistent.

When using HTTP, the request body typically contains the **query**, **operationName**, and **variables** properties:

~~~json
{
    "query": "query GetBook($id: ID!) { book(id: $id) { id title } }",
    "operationName": "GetBook",
    "variables": {
        "id": "book-101"
    }
}
~~~

Exact request packaging also depends on the HTTP endpoint and transport configured by the application.

### 4.4. Mutation operation

With the schema above, a client can create a book as follows:

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
    createBook(input: $input) {
        id
        title
        status
        author {
            id
            name
        }
    }
}
~~~

Variables:

~~~json
{
    "input": {
        "title": "Practical GraphQL",
        "authorId": "author-12",
        "publishedYear": 2026
    }
}
~~~

The **CreateBookInput** name in the variable declaration must match the input type exposed by the schema. Required fields such as **title** and **authorId** must be present and non-null. **publishedYear** can be omitted because the schema does not mark it non-null.

A mutation can only be invoked when the **createBook** field is declared on the **Mutation** root type and the server has a handler for that field. Simply having the field appear in SDL does not create the book-saving logic by itself.

### 4.5. Subscription operation

The client subscribes to events with an operation:

~~~graphql
subscription OnBookAdded {
    bookAdded {
        id
        title
        author {
            name
        }
    }
}
~~~

The client keeps the subscription open over the configured transport. Each time the server emits a valid event, the client receives a result structured according to the selection set above. The client must also handle connection closures, stream errors, and unsubscribing when it no longer needs events.

## 5. Features for reusing operations

### 5.1. Alias

An alias assigns a different name to a field in the response. It is useful when calling the same field multiple times with different arguments:

~~~graphql
query CompareBookLists {
    newest: books(limit: 5) {
        id
        title
    }
    moreBooks: books(limit: 20) {
        id
        title
    }
}
~~~

The response will have two keys, **newest** and **moreBooks**. Aliases only rename the key in the result; they do not change the field name in the schema.

### 5.2. Fragment

A fragment groups a selection set for reuse:

~~~graphql
fragment BookSummary on Book {
    id
    title
    status
}

query GetBookSummaries {
    books(limit: 10) {
        ...BookSummary
    }
}
~~~

**on Book** specifies the type to which the fragment applies. Fragments help avoid repeating field lists when multiple operations or multiple locations need the same data structure.

A union groups multiple object types that a field can return; an interface describes a shared set of fields implemented by multiple object types. When querying a union or interface, inline fragments allow selecting fields for specific types. In the example below, the schema adds a union and a search field on Query:

~~~graphql
union SearchResult = Book | Author

extend type Query {
    searchCatalog: [SearchResult!]!
}
~~~

An operation can select the appropriate fields for each result type:

~~~graphql
query SearchCatalog {
    searchCatalog {
        __typename
        ... on Book {
            id
            title
        }
        ... on Author {
            id
            name
        }
    }
}
~~~

In the example, **searchCatalog** can return multiple types. **__typename** indicates the concrete type of each result; inline fragments only request fields valid on the corresponding type.

### 5.3. Directives

Directives modify how part of an operation is processed. Two common directives are **@include** and **@skip**:

~~~graphql
query GetBook($id: ID!, $showStatus: Boolean!) {
    book(id: $id) {
        id
        title
        status @include(if: $showStatus)
        author {
            name
        }
    }
}
~~~

- **@include(if: true)** keeps the field in the result; **false** omits the field.
- **@skip(if: true)** omits the field; **false** keeps the field.

GraphQL also has schema-level directives, such as **@deprecated**, to mark legacy fields or enum values:

~~~graphql
type Book {
    id: ID!
    title: String!
    oldTitle: String @deprecated(reason: "Use title instead")
}
~~~

Marking a field as deprecated gives clients time to migrate to the new field before the server removes the old one.

## 6. Responses and how GraphQL reports errors

A successful response typically has a **data** property:

~~~json
{
    "data": {
        "book": {
            "id": "book-101",
            "title": "Practical GraphQL"
        }
    }
}
~~~

The data structure in **data** mirrors the operation's selection set. If the client only requests **id** and **title**, the response does not need to return other fields of **Book**.

GraphQL distinguishes validation errors from runtime execution errors:

- **Parse or validation errors** occur when the document has syntax errors or the operation does not match the schema, such as a non-existent field, wrong argument type, or missing selection set. The server does not execute an invalid operation.
- **Execution errors** occur when a field encounters a problem while executing, such as data not found or an exception in a downstream service. The response can contain both **data** and **errors**.

Example of a field failing to retrieve data:

~~~json
{
    "data": {
        "book": null
    },
    "errors": [
        {
            "message": "Book not found",
            "path": ["book"]
        }
    ]
}
~~~

This is an illustrative example of the response structure; the actual message depends on how the application handles and translates exceptions. When inspecting errors, check **message**, **path**, and **data** together to determine which field failed and which parts of the data are still usable.

Nullability directly affects how much data becomes null when an error occurs. If a non-null field cannot produce a value, GraphQL propagates null up to the nearest nullable parent field and records an error. Therefore, **!** declarations should reflect the server's actual guarantees.

## 7. Bringing schemas and operations into Spring for GraphQL

In a Spring Boot application using Spring for GraphQL, SDL schemas are typically placed in the resources directory:

~~~text
src/
└── main/
    └── resources/
        └── graphql/
            ├── schema.graphqls
            └── catalog.graphqls
~~~

Schema files can be discovered by Spring Boot and merged into the application schema according to schema location configuration. Splitting the schema into multiple files helps organize by business domain, though the merged types and fields must still form a valid GraphQL schema.

Spring for GraphQL connects schema fields to handler methods via annotations. Example:

~~~java
@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    Book book(@Argument String id) {
        return bookService.findById(id);
    }

    @MutationMapping
    Book createBook(@Argument CreateBookInput input) {
        return bookService.create(input);
    }
}
~~~

In the example:

- **@QueryMapping** maps the method to the **book** field on the **Query** root type.
- **@MutationMapping** maps the method to the **createBook** field on the **Mutation** root type.
- **@Argument** extracts the argument value from the operation and converts it to the corresponding Java type.

The method name is typically used to infer the field name. You can specify the field name explicitly in the annotation when needed. **CreateBookInput** is a Java class or record with a structure compatible with the input object in SDL.

When clients request nested fields such as **Book.author**, GraphQL needs to know how to obtain the value of that field. Spring for GraphQL can use default property access or a method mapped with **@SchemaMapping**. Details on resolvers for nested fields, handling relationships, and optimizing data loading are covered in subsequent advanced lessons.

For Subscriptions, the method is mapped with **@SubscriptionMapping** and must provide a stream-based publisher compatible with the application model. In addition to the resolver, the server needs a transport configured to support subscriptions so clients can receive multiple results over a single subscription.

You can test an operation using **GraphQlTester** in tests:

~~~java
graphQlTester.document("""
    query GetBook($id: ID!) {
        book(id: $id) {
            id
            title
        }
    }
    """)
    .variable("id", "book-101")
    .execute()
    .path("book.title")
    .entity(String.class)
    .isEqualTo("Practical GraphQL");
~~~

This test sends an operation with a variable, executes it through the GraphQL runtime, and asserts a field in the response. It verifies the schema, operation, and field execution path together at an integration level.

## 8. Design and testing workflow

When building a GraphQL feature, you can follow this sequence:

1. **Identify client needs.** What data does the client need to read or modify? Which fields actually need to appear in the response?
2. **Design output types.** Describe the objects and relationships clients are allowed to query. Use scalars and enums with clear meanings.
3. **Design root fields.** Place read operations on **Query**, data modifications on **Mutation**, and event streams on **Subscription**.
4. **Design arguments and inputs.** Mark required fields intentionally; group mutation data into input objects when appropriate.
5. **Write sample operations.** Use variables for dynamic data, name operations, and select only the necessary fields.
6. **Connect handlers in Spring.** Ensure every exposed field has a proper way to fetch or compute its value.
7. **Test responses and errors.** Test existing data, missing data, invalid input, nullable fields, and service error cases.

Several principles keep schemas easy to use and evolve:

- Name types and fields using business domain language; field names should describe specific data or actions.
- Do not expose database structure directly if it is not a suitable contract for clients.
- Only mark fields non-null when the server can guarantee the value will always exist.
- Prefer input objects for mutations with multiple related parameters.
- Design nested fields deliberately; a single operation can request many levels of data and create heavy load if the server does not constrain it.
- When changing an actively used schema, adding new fields is usually less disruptive than deleting or renaming existing fields. Mark fields as deprecated and give clients time to migrate before removing old fields.
- Do not treat a field's presence in SDL as proof that the field is implemented. Schema, handlers, and data sources must stay consistent.

## 9. Common pitfalls

| Situation | Cause | Resolution |
| --- | --- | --- |
| **Cannot query field ...** | The field does not exist on the queried type | Verify the exact type and field name in the schema |
| **Field ... must have a selection of subfields** | The field returns an object, but the operation does not select subfields | Add a selection set |
| **Field ... must not have a selection since type ... has no subfields** | The operation selects subfields on a scalar or enum | Remove the nested selection set |
| **Variable ... of required type ... was not provided** | Missing required variable | Supply the variable or adjust the contract if it is genuinely optional |
| **Variable ... is of type ... but used where ... is expected** | Variable type is incompatible with the argument | Align the variable declaration type with the schema |
| Field exists in schema but fails at runtime | Missing handler or data source throws an error | Check mappings, services, and exceptions |
| Response has a **null** field accompanied by **errors** | Field execution failed or nullability propagated null to parent | Inspect **errors.path**, check data, and review nullability design |

## 10. Summary

The schema defines the typed data contract and entry points exposed by a GraphQL API. Operations use that contract to request the exact data or action needed. SDL provides object types, scalars, enums, input types, arguments, lists, and nullability; Query, Mutation, and Subscription define the three primary interaction modes.

In Spring for GraphQL, schemas are placed in application resources and fields are wired to handler methods using the corresponding annotations. When the schema, operations, and handlers are aligned, clients can choose the exact data they receive, while the server has a clear contract to validate, execute, and evolve the API.
