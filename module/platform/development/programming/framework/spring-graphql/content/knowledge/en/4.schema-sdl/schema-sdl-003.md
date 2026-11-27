# type Mutation

In GraphQL, `type Mutation` declares operations that can modify system state, such as creating an order, updating a profile, confirming a payment, or deleting a resource. It is part of the SDL schema, describing the commands clients are allowed to request and the data types the server returns.

In Spring for GraphQL, fields declared in the root mutation type are typically mapped to Java methods using `@MutationMapping`. The starter provides the execution foundation, while the schema and resolvers still need to be designed around business requirements.

## 1. What is a Mutation?

GraphQL defines three common operation types:

- `query` reads data.
- `mutation` requests a modification with side effects.
- `subscription` receives events or updates over time.

The mutation root type is an object type in the schema. By common convention, this object type is named `Mutation`:

```graphql
type Query {
    book(id: ID!): Book
}

type Mutation {
    createBook(title: String!): Book!
    deleteBook(id: ID!): Boolean!
}

type Book {
    id: ID!
    title: String!
}
```

The schema above exposes two operations: creating a book and deleting a book. Clients do not call a separate URL per mutation; instead, the client sends a GraphQL operation to the endpoint and selects the field to execute.

A GraphQL schema must have a query root type, whereas a mutation root type is optional. A read-only API may omit `type Mutation`. When a schema includes mutations, the root type must be an object type with at least one field.

The name `Mutation` is a default convention. If you want to use a different name, you must explicitly map the root operation type in the schema:

```graphql
schema {
    query: RootQuery
    mutation: Commands
}

type RootQuery {
    book(id: ID!): Book
}

type Commands {
    createBook(title: String!): Book!
}
```

Here `Commands` is the schema's mutation root type, even though the type name is not `Mutation`.

## 2. Declaring fields in type Mutation

Each field in `type Mutation` represents an operation a client can request. A field can accept arguments and return a scalar, enum, or object type.

Example:

```graphql
type Mutation {
    createBook(title: String!, author: String!): Book!
    renameBook(id: ID!, newTitle: String!): Book!
    publishBook(id: ID!): Book!
    deleteBook(id: ID!): Boolean!
}
```

When designing fields, express business intent with clear names such as `createBook`, `publishBook`, or `cancelOrder`. Names like `update`, `execute`, or `process` do not tell clients what change they are requesting.

Arguments should describe the minimal data required for the command. Use `ID!` for identifiers, appropriate scalars for simple values, and input objects when an operation takes multiple fields.

The return type should reflect what the client needs to update the UI or continue the business workflow. Returning `Boolean!` may suffice for a simple operation, but an object payload is often more useful because the client can receive the newly created entity, new state, or validation error details.

## 3. Using input objects for input data

When a mutation takes multiple arguments, grouping them into an `input` type keeps the schema clean and extensible. GraphQL clearly distinguishes output object types from input object types used for incoming data.

Example:

```graphql
input CreateBookInput {
    title: String!
    authorName: String!
    isbn: String
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
}
```

The client sends the operation and variables:

```graphql
mutation CreateBook($input: CreateBookInput!) {
    createBook(input: $input) {
        id
        title
        authorName
    }
}
```

Variables are passed separately from the document:

```json
{
  "input": {
    "title": "Practical GraphQL",
    "authorName": "Nguyen An",
    "isbn": "9780000000001"
  }
}
```

Input objects have important restrictions:

- Fields of an input object must use valid input types such as scalars, enums, other input objects, or lists of input types.
- You cannot use an output object type like `Book` as the field type in an `input`.
- Input objects do not have field resolvers or arguments like output object fields.
- You can use `!` to require clients to provide a value and set default values where appropriate.

The following example is invalid because `Book` is an output object type:

```graphql
input InvalidBookInput {
    book: Book
}
```

If you need to pass a nested structure, define a dedicated input type:

```graphql
input AuthorInput {
    name: String!
    email: String
}

input CreateBookInput {
    title: String!
    author: AuthorInput!
}
```

Do not reuse output types as inputs merely to avoid declaring another type. Data clients are allowed to send and data the server is allowed to return usually have different purposes, permissions, and lifecycles.

## 4. Nullability and the semantics of input data

The `!` symbol indicates a value cannot be null. For an input argument or input field, this means the client must supply a valid value of the declared type unless a suitable default value exists.

```graphql
input UpdateBookInput {
    title: String!
    subtitle: String
}

type Mutation {
    updateBook(id: ID!, input: UpdateBookInput!): Book!
}
```

In this example, `title` is required and non-null. `subtitle` is optional and may receive `null`. For partial update operations, agree on the semantics of three states:

1. Field omitted from input: the client does not request changing that field.
2. Field present with a value: update to the new value.
3. Field present with `null`: depending on the contract, may request clearing the current value.

Not every Java type preserves the distinction between an omitted field and an explicitly sent `null`. If business logic needs to distinguish between them, the resolver must use an argument representation that tracks field presence or an appropriate binding mechanism rather than relying solely on a nullable Java property.

Output nullability is also important. For example, `Book!` guarantees the mutation returns a non-null `Book` object upon successful execution. If the server cannot return the object due to a business error, you can design a payload with a nullable `book` field and a structured list of errors.

## 5. Designing return payloads

A real-world mutation often needs to return more than one value. A payload can contain the resulting entity alongside business errors that the client can display or handle.

Example:

```graphql
input CreateBookInput {
    title: String!
    authorName: String!
}

type UserError {
    field: String
    code: String!
    message: String!
}

type BookPayload {
    book: Book
    userErrors: [UserError!]!
}

type Mutation {
    createBook(input: CreateBookInput!): BookPayload!
}
```

`BookPayload!` guarantees the server returns a payload. `book` may be `null` if the operation fails due to validation errors; `userErrors` is always a list, even when empty.

Clients can select the exact information they need:

```graphql
mutation CreateBook($input: CreateBookInput!) {
    createBook(input: $input) {
        book {
            id
            title
        }
        userErrors {
            field
            code
            message
        }
    }
}
```

One possible response convention is:

- Success: `book` holds data and `userErrors` is an empty list.
- Invalid input: `book` is `null` and `userErrors` describes the violated fields or rules.
- Unexpected system error: raise a GraphQL error according to the server's error-handling policy.

Payloads are a design choice, not a mandatory requirement of GraphQL. For very simple operations, returning an entity or scalar directly may be enough. Choose a contract that gives clients the information they need without requiring follow-up queries just to see the result of what was created.

## 6. Sending mutation operations

A mutation operation starts with the `mutation` keyword, and may include an operation name and variable declarations:

```graphql
mutation RenameBook($id: ID!, $title: String!) {
    renameBook(id: $id, newTitle: $title) {
        id
        title
    }
}
```

Variables:

```json
{
  "id": "book-42",
  "title": "Advanced GraphQL"
}
```

If variables are not needed, values can be written inline in the document, though variables are typically easier to reuse, test, and pass safely when clients construct requests.

A mutation operation can contain multiple top-level fields:

```graphql
mutation {
    first: renameBook(id: "book-1", newTitle: "New Title 1") {
        id
    }
    second: renameBook(id: "book-2", newTitle: "New Title 2") {
        id
    }
}
```

The `first` and `second` aliases distinguish two results calling the same field. Top-level mutation fields within a single operation are executed sequentially in the order they appear in the document. This rule ensures later operations see the effects of earlier ones in the same operation.

However, sequential execution does not mean the entire operation automatically runs inside a single database transaction. If the second field fails, GraphQL does not automatically roll back the side effects of the first field. Transaction boundaries must be designed in the service or persistence layer according to business requirements.

## 7. Mutation root and execution order

GraphQL processes query fields using standard execution mechanics, where fields can be resolved in parallel if the runtime permits. Top-level mutation fields, by contrast, must be executed sequentially.

Example:

```graphql
mutation Checkout {
    reserveInventory(orderId: "order-10") {
        reservationId
    }
    confirmOrder(orderId: "order-10") {
        status
    }
}
```

`confirmOrder` executes only after `reserveInventory` completes within the same operation. Even so, this design makes sense only if the API intentionally allows clients to compose two commands in sequence. For critical workflows requiring atomicity, consider a single business mutation such as `checkoutOrder` so the server coordinates all steps inside an appropriate transaction or workflow.

Mutations are commands with side effects. Therefore:

- Do not place data-writing operations inside query resolvers.
- Do not assume a client sends a mutation only once; timeouts and retries can resend requests.
- For operations that create payments, place orders, or transition states with duplication risk, consider idempotency keys and duplicate-execution guards.
- Use transactions, optimistic locking, or appropriate coordination mechanisms when business logic requires consistency.

## 8. Mapping type Mutation with Spring for GraphQL

After declaring fields in SDL, Spring for GraphQL can map fields on the mutation root type to Java methods using `@MutationMapping`.

With the schema:

```graphql
input CreateBookInput {
    title: String!
    authorName: String!
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
}

type Book {
    id: ID!
    title: String!
    authorName: String!
}
```

The controller can be written as follows:

```java
package com.example.graphql.book;

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
    public Book createBook(@Argument CreateBookInput input) {
        return bookService.create(input);
    }
}
```

`@MutationMapping` maps the method to the identically named field on the mutation root type. `@Argument` binds the input object from the `input` argument and converts it to the corresponding Java type. The field name can be specified explicitly if the method name differs from the SDL name:

```java
@MutationMapping(name = "createBook")
public Book add(@Argument CreateBookInput input) {
    return bookService.create(input);
}
```

The input DTO can be a Java record:

```java
public record CreateBookInput(
    String title,
    String authorName
) {}
```

The controller should focus on receiving input and delegating to the service. Business rules, duplicate ISBN checks, state validation, and data persistence belong in the service or domain layer so they can be reused across different interfaces.

If the schema returns a payload, the method can return a matching DTO:

```java
public record UserError(String field, String code, String message) {}

public record BookPayload(Book book, List<UserError> userErrors) {}
```

Java types must match the nullability and structure published by SDL. An output field declared with `!` must not return `null` during successful execution.

## 9. Validation, authorization, and error handling

GraphQL validates operation structure and data types against the schema, but the schema does not replace business validation. For example, `title: String!` only requires a non-null string; it does not guarantee the title is non-blank, within length limits, or unique against existing records.

The server needs to enforce at least these layers of checks:

1. **Structural validation**: whether inputs have the right types, required fields are supplied, and enums have valid values. The GraphQL engine handles most schema-based checks.
2. **Business validation**: whether data satisfies domain rules and whether the current state permits the operation.
3. **Authorization**: whether the current user has permission to execute the command on the specific resource.
4. **Concurrency**: whether the data was modified by another request since the client read it.

Never trust a client-supplied ID as proof of ownership. The server must check permissions on the accessed object while avoiding sensitive details in error messages.

For predictable errors such as a missing title or invalid ISBN, a `userErrors` payload helps clients display field-level errors. For authentication, authorization, or system errors, the server must apply a consistent exception-handling policy. Do not expose stack traces, SQL queries, or infrastructure details to clients.

If using Bean Validation, you can combine annotations on input DTOs with appropriate validation configuration in the application. Regardless of the mechanism, the service/domain layer must still protect invariants because commands may be invoked from multiple entry points.

## 10. Common design mistakes

| Issue | Consequence | How to address |
| --- | --- | --- |
| Using an output object as an input field | Invalid schema | Create a separate input object type |
| Naming mutations too generically | Clients struggle to understand the command's effect | Use names expressing the business action |
| Returning `Boolean` for every operation | Clients must issue extra queries to fetch new data | Return the needed entity or payload |
| Using `String!` instead of structured input | Hard to type-check and evolve the contract | Declare appropriate input objects and scalars |
| Assuming sequential mutations form a transaction | May leave partial updates on failure | Define transaction boundaries in the service |
| Skipping resource-level permission checks | Users can modify other users' data | Enforce authorization in service/domain or data access |
| Ignoring retries | Duplicate records or payments created | Design idempotency for applicable commands |
| Returning internal errors directly | Leaks system internals | Standardize errors and expose only safe information |

## 11. Checklist for designing a mutation

Before publishing a new mutation, verify:

- Does the field name accurately describe the business command?
- Are arguments grouped into an input object when the structure is large enough?
- Do input types clearly distinguish required and optional data?
- Does the client receive enough result data to update the UI?
- Are validation errors structured and displayable?
- Is access control checked for both the operation and target resource?
- Have retries, transactions, and concurrent updates been considered?
- Does the resolver delegate business logic to the service/domain layer?

`type Mutation` is the contract for state-changing commands. Good design clearly expresses business intent, defines typed inputs and outputs, enforces access control, and handles errors predictably. In Spring for GraphQL, SDL describes the command while `@MutationMapping` connects that command to the executing service. Separating these two roles keeps the schema understandable for clients and keeps business logic independently testable and reusable.
