# Input Objects for Mutations

Mutations often need multiple input values to create or update a resource. If every value is declared as a separate argument, the field signature becomes long, hard to evolve, and difficult to reuse. GraphQL solves this with **input objects**: a dedicated data type for grouping input values into a named, strongly typed structure.

In Spring for GraphQL, an input object is declared in SDL, and Spring binds the argument to a Java record, DTO, or matching data structure via **@Argument**. Separating input objects from output object types lets the server control exactly what data clients are allowed to send, apply validation, and protect internal models.

This lesson focuses on designing input objects for mutations, passing data with variables, understanding null/default rules, binding to Java, validating input, and handling create and update scenarios.

## 1. Why do mutations need input objects?

A simple mutation can declare each argument directly:

~~~graphql
type Mutation {
  createBook(
    title: String!
    authorId: ID!
    status: String
    description: String
  ): Book!
}
~~~

As the number of fields grows, the field ends up with too many arguments. Every time a property is added, the mutation signature changes. Clients also have to pass a loose group of values even though, from a business perspective, they describe a single book-creation request.

Those values can be grouped into an input object:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
  status: BookStatus = DRAFT
  description: String
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

Now the mutation accepts only one **input** argument. The fields belonging to the book creation request are described centrally inside **CreateBookInput**.

Input objects provide several benefits:

- Group values belonging to the same business command.
- Clearly express the type and requiredness of each field.
- Make it easier to extend when adding input fields.
- Allow nesting input objects to describe complex structures.
- Separate data clients are allowed to send from data the server returns or internal persistence models.
- Simplify binding into Java records/DTOs and applying validation.

## 2. Declaring input objects in SDL

An input object is declared with the **input** keyword:

~~~graphql
input InputTypeName {
  fieldName: InputFieldType
}
~~~

Example:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
  description: String
}
~~~

An input object must have at least one input field. Each field has a name, an input type, and optionally a default value.

### Types allowed in input objects

Input fields may only use valid input types:

- Scalars such as **String**, **Int**, **Float**, **Boolean**, **ID**, and custom scalars.
- Enums such as **BookStatus**.
- Other input objects.
- Lists and non-nulls wrapping a valid input type.

Example:

~~~graphql
enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

input BookMetadataInput {
  language: String
  pageCount: Int
  keywords: [String!]
}

input CreateBookInput {
  title: String!
  authorId: ID!
  status: BookStatus
  metadata: BookMetadataInput
}
~~~

Regular object types, interfaces, or unions cannot be used as the field type of an input object. Those types describe output data. When a client needs to reference an existing object, it usually only needs to send an identifier such as **authorId** instead of sending the entire **Author** object.

The following schema is invalid:

~~~graphql
type Author {
  id: ID!
  name: String!
}

input CreateBookInput {
  title: String!
  author: Author
}
~~~

Replace it with an input type or an ID:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
}
~~~

The server uses **authorId** to load the Author, check permissions, and create the relationship. The client should not be able to supply Author properties that the book creation operation has no permission to change.

## 3. Connecting input objects to mutations

A mutation field accepts an input object as an argument and returns an output type:

~~~graphql
type Book {
  id: ID!
  title: String!
  status: BookStatus!
}

input CreateBookInput {
  title: String!
  authorId: ID!
  status: BookStatus = DRAFT
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

There are three parts to distinguish:

1. **CreateBookInput** defines the structure of data the client sends.
2. **input: CreateBookInput!** declares the required argument of the mutation.
3. **Book!** is the output type the server returns after processing.

An input object is not the result of a mutation. The client still needs a selection set on the output object to specify which fields it wants to receive:

~~~graphql
mutation {
  createBook(input: {
    title: "GraphQL with Spring"
    authorId: "author-01"
  }) {
    id
    title
    status
  }
}
~~~

In this example, **input** is the input argument; the block inside braces after **createBook** is the selection set of the **Book** result.

### Use one input object per business action

Creating and updating usually have different requiredness rules. Therefore, design separate inputs:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
}

input UpdateBookInput {
  id: ID!
  title: String
  description: String
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
  updateBook(input: UpdateBookInput!): Book
}
~~~

When creating, **title** and **authorId** are required. When updating, the client can send only the fields that need to change; other fields can be preserved according to the API's rules.

Avoid creating a single generic input containing every property of Book and reusing it across all mutations. Separate inputs per use case keep the API contract clear, limit mass assignment, and prevent clients from accidentally sending unrelated fields.

## 4. Passing input objects with variables

You can write an input object inline in an operation, but in real-world applications prefer variables. This separates the GraphQL document from concrete data:

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
  createBook(input: $input) {
    id
    title
    status
  }
}
~~~

Variables are sent as JSON:

~~~json
{
  "input": {
    "title": "GraphQL with Spring",
    "authorId": "author-01",
    "status": "DRAFT"
  }
}
~~~

The variable **input** is declared with type **CreateBookInput!**, then passed to the mutation argument of the same name. The server validates variables against the schema before invoking the resolver.

### Literals and JSON variables have different syntax

In a GraphQL document, enums are written as unquoted enum literals:

~~~graphql
mutation {
  createBook(input: {
    title: "GraphQL with Spring"
    authorId: "author-01"
    status: DRAFT
  }) {
    id
  }
}
~~~

In JSON variables, enums are passed as strings:

~~~json
{
  "input": {
    "title": "GraphQL with Spring",
    "authorId": "author-01",
    "status": "DRAFT"
  }
}
~~~

This is a difference between GraphQL syntax and JSON. If you write **"DRAFT"** as a string literal in a GraphQL document, the value is no longer an enum literal and the operation may be invalid.

Variables also let clients reuse the same document across multiple data sets, avoid string concatenation to build queries, and reduce escaping errors.

## 5. Required, nullable, and default values

When designing an input object, understand three states accurately: required field, optional field, and field with a default value.

~~~graphql
input CreateBookInput {
  title: String!
  subtitle: String
  status: BookStatus = DRAFT
  tags: [String!] = []
}
~~~

Meaning:

| Field | Rule |
|---|---|
| **title: String!** | Must be provided and cannot be null |
| **subtitle: String** | Can be omitted or passed null |
| **status: BookStatus = DRAFT** | If omitted, uses DRAFT; if passed null, remains null because the field is nullable |
| **tags: [String!] = []** | If omitted, uses an empty list; elements in the list cannot be null |

An input field's default value is declared after **=**. Default values save clients from having to send values that have stable default rules.

### Distinguishing omitted fields from passing null

GraphQL distinguishes a field not appearing in an input object from a field explicitly sent as **null**.

With the input object:

~~~graphql
input UpdateBookInput {
  id: ID!
  title: String
  description: String
}
~~~

If the client sends:

~~~json
{
  "input": {
    "id": "book-01",
    "title": "New Title"
  }
}
~~~

The **description** field is not provided. After coercion, a nullable field without a default is omitted from the input value map.

If the client sends:

~~~json
{
  "input": {
    "id": "book-01",
    "title": "New Title",
    "description": null
  }
}
~~~

The **description** field was provided with a null value. If update logic distinguishes the two cases, the server can interpret them as:

- Omitting **description**: keep the current description.
- Sending **description: null**: clear the current description.

This point is crucial for patch-style mutations. Do not assume every Java null has the same meaning, because when binding to a regular DTO, an omitted field and a field passed as null can both become Java null.

### Default values on input fields and arguments

Defaults can be declared on individual fields:

~~~graphql
input CreateBookInput {
  status: BookStatus = DRAFT
}
~~~

Or defaults on the mutation argument:

~~~graphql
type Mutation {
  createDraftBook(status: BookStatus = DRAFT): Book!
}
~~~

An input field default is applied when that field does not appear in the input object. An argument default is applied when the argument is not provided. Avoid placing conflicting defaults at multiple levels, as clients will find it hard to tell which final value is used.

If a non-null field has a valid default, the client can omit that field and the server uses the default. If the client explicitly passes null for a non-null field, the operation is rejected during coercion.

## 6. Nested input objects and lists

An input object can contain another input object. This works well when a mutation accepts multiple groups of structured data:

~~~graphql
input AddressInput {
  street: String!
  city: String!
  postalCode: String
}

input BookMetadataInput {
  language: String
  pageCount: Int
  keywords: [String!]
}

input CreateBookInput {
  title: String!
  authorId: ID!
  shippingAddress: AddressInput
  metadata: BookMetadataInput
}
~~~

The client can send nested structures in JSON:

~~~json
{
  "input": {
    "title": "GraphQL with Spring",
    "authorId": "author-01",
    "shippingAddress": {
      "street": "12 Nguyen Hue",
      "city": "Ho Chi Minh City",
      "postalCode": "700000"
    },
    "metadata": {
      "language": "vi",
      "pageCount": 320,
      "keywords": ["graphql", "spring", "api"]
    }
  }
}
~~~

### Input objects in lists

An input object can also be an element of a list:

~~~graphql
input ChapterInput {
  title: String!
  position: Int!
}

input CreateBookInput {
  title: String!
  authorId: ID!
  chapters: [ChapterInput!]!
}
~~~

The client sends multiple chapters:

~~~json
{
  "input": {
    "title": "GraphQL with Spring",
    "authorId": "author-01",
    "chapters": [
      {
        "title": "GraphQL fundamentals",
        "position": 1
      },
      {
        "title": "Spring integration",
        "position": 2
      }
    ]
  }
}
~~~

With **[ChapterInput!]!**, the list cannot be null and each element cannot be null. An empty list is still a valid value if there are no other business rules. If at least one chapter is required, the server needs additional business validation.

### Recursive input objects

An input object can reference another input object, including itself, as long as the structure does not form an unbroken chain of single non-null fields requiring an infinite value:

~~~graphql
input CategoryInput {
  name: String!
  parent: CategoryInput
  children: [CategoryInput!]
}
~~~

This example represents a category tree. The **parent** field is nullable so the client can terminate the recursive branch. A direct reference cycle consisting solely of non-null fields such as **next: NodeInput!** could never form a finite input value and is invalid under GraphQL schema rules.

Only use deeply nested inputs when they reflect a clear business structure. For data referencing an existing resource, sending an ID is usually simpler and safer than repeating the entire object.

## 7. Spring for GraphQL binds input objects to Java

After GraphQL validates and coerces variables, Spring for GraphQL binds arguments to controller Java parameters. With **@Argument**, the argument name in SDL is mapped to a method parameter.

Example input schema:

~~~graphql
enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

input CreateBookInput {
  title: String!
  authorId: ID!
  status: BookStatus = DRAFT
  tags: [String!] = []
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

Java record:

~~~java
public record CreateBookInput(
        String title,
        String authorId,
        BookStatus status,
        List<String> tags) {
}
~~~

Controller:

~~~java
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

**@MutationMapping** maps the method to the **Mutation.createBook** field. **@Argument("input")** tells Spring to bind the **input** argument into **CreateBookInput**. Spring GraphQL supports binding into a constructor or properties of a suitable Java type; records are a concise choice because they provide a canonical constructor and represent input data immutably.

Java DTO field names must match the input field names or be configured for binding accordingly. Java types must also match the GraphQL types: **ID** typically binds to **String**, enums bind to the matching Java enum, lists bind to collections/arrays, and nested input objects bind to nested DTOs.

### Binding nested inputs

With a schema containing **AddressInput**, you can create a matching Java record:

~~~java
public record AddressInput(
        String street,
        String city,
        String postalCode) {
}

public record CreateBookInput(
        String title,
        String authorId,
        AddressInput shippingAddress) {
}
~~~

Spring binds the nested structure into the corresponding parameter. The controller can convert the input into a command or call the service:

~~~java
@MutationMapping
public Book createBook(@Argument("input") CreateBookInput input) {
    CreateBookCommand command = new CreateBookCommand(
            input.title(),
            input.authorId(),
            input.shippingAddress());

    return bookService.create(command);
}
~~~

In larger applications, consider translating the GraphQL input DTO into an application/service layer command. That way the service does not depend directly on the API structure and can be invoked from other adapters.

## 8. Validation for input objects

GraphQL has multiple layers of input data checking. Distinguish schema-level validation from application-level validation.

### Schema validation and input coercion

GraphQL automatically checks:

- Whether the field exists on the input object.
- Whether required fields are provided.
- Whether values match the declared scalar, enum, list, or input object.
- Whether null is passed to a non-null field.
- Whether literals or variables can be coerced to the required type.

For example, schema:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
}
~~~

Variables missing **title** or passing **authorId: null** will be rejected before the resolver executes. Clients also cannot send arbitrary fields like **internalCost** if that field is not declared on the input type.

### Bean Validation

The schema only checks structure and data types. It cannot fully express rules such as strings not containing only whitespace, author IDs having to exist, or chapter counts falling within business bounds.

You can use Jakarta Bean Validation on Java inputs:

~~~java
public record CreateBookInput(
        @NotBlank String title,
        @NotBlank String authorId,
        BookStatus status,
        List<@NotBlank String> tags) {
}
~~~

The controller marks the argument to validate:

~~~java
@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public Book createBook(
            @Argument("input") @Valid CreateBookInput input) {
        return bookService.create(input);
    }
}
~~~

The application needs a Jakarta Bean Validation provider, typically added via **spring-boot-starter-validation**. With Spring Boot 3, annotations live in the **jakarta.validation** namespace.

Commonly used constraints:

| Constraint | Purpose |
|---|---|
| **@NotNull** | Value cannot be null |
| **@NotBlank** | String must contain at least one non-whitespace character |
| **@NotEmpty** | String, collection, or map cannot be empty |
| **@Size** | Limits length or element count |
| **@Min / @Max** | Numeric integer bounds |
| **@Email** | Basic email format validation |
| **@Pattern** | Validation against a regular expression |

For nested inputs, use **@Valid** on properties that require cascading validation and appropriate constraints on child fields. Check your application's validation configuration to ensure constraints are enforced at the intended level.

### Business validation in the service

Some rules can only be checked when accessing data or executing business logic:

- Does **authorId** exist?
- Does the current user have permission to create a book for that author?
- Does the book title conflict under catalog rules?
- Does the chapter list have duplicate positions?
- Is the allowed initial status **DRAFT** or **PUBLISHED**?

These checks belong in the application/service layer and should run within the appropriate business workflow. Do not treat GraphQL's acceptance of an input as proof that the data is valid under business rules.

## 9. Distinguishing schema, binding, and business errors

A mutation request can fail at several stages:

| Stage | Example error | Has resolver run? |
|---|---|---:|
| Parse/operation validation | Syntax error, non-existent input field | No |
| Variable/input coercion | Missing non-null field, invalid enum | No |
| Binding/Bean Validation | DTO fails to bind or constraint fails | May not enter method body |
| Business validation | Author does not exist or user lacks permission | Yes |
| Persistence/external call | Database constraint or external service error | Yes |

GraphQL returns errors via the **errors** array. For a mutation returning non-null **Book!**, if the resolver throws an error and there is no fallback value, null propagation may cause the mutation field and the **data** section to become null according to GraphQL rules.

Example response:

~~~json
{
  "data": {
    "createBook": null
  },
  "errors": [
    {
      "message": "Author not found",
      "path": ["createBook"],
      "extensions": {
        "code": "AUTHOR_NOT_FOUND"
      }
    }
  ]
}
~~~

In Spring for GraphQL, you can standardize exceptions into GraphQL errors using **@GraphQlExceptionHandler** or **DataFetcherExceptionResolver** depending on scope. Avoid returning stack traces, SQL, or internal details to clients. Technical details should be logged safely on the server, while the response contains only enough information for the client to handle.

## 10. Input objects for update mutations

Creation usually requires all mandatory fields; updates usually change only a subset. Therefore, **UpdateBookInput** typically has a different structure:

~~~graphql
input UpdateBookInput {
  id: ID!
  title: String
  description: String
  status: BookStatus
}

type Mutation {
  updateBook(input: UpdateBookInput!): Book
}
~~~

Example changing only the title:

~~~json
{
  "input": {
    "id": "book-01",
    "title": "New Book Title"
  }
}
~~~

Example clearing the description if the API defines null to mean clear:

~~~json
{
  "input": {
    "id": "book-01",
    "description": null
  }
}
~~~

### Preserving omitted and null semantics when binding to Java

With a regular Java record:

~~~java
public record UpdateBookInput(
        String id,
        String title,
        String description,
        BookStatus status) {
}
~~~

An omitted **title** field and a **title** field sent with null can both end up represented as Java null after binding. If business logic needs to distinguish those two states, use a representation that preserves whether the field was present, such as a map checking key presence, or a presence-aware mechanism like **ArgumentValue** at argument positions supported by Spring GraphQL.

**ArgumentValue<T>** is used to distinguish an argument that was not provided from one that was provided with a null value. For nested input objects, verify binding and presence representation at the appropriate level for your Spring GraphQL version; do not assume a regular nullable Java field automatically retains this information.

Another design approach is to avoid ambiguous patches. For example, split clearing a description into an explicit mutation or use an input with a specific action. This makes the API clearer when clients need to control multiple update states.

## 11. Security and input data control

Input objects form the boundary of data clients are allowed to send. Input design should follow the principle of accepting only fields needed for the use case.

For example, avoid declaring:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
  ownerId: ID
  createdAt: String
  approved: Boolean
  internalCost: Float
}
~~~

If **ownerId**, **createdAt**, **approved**, or **internalCost** are server-managed, clients should not be allowed to specify them during book creation. The server should derive the owner from the authenticated principal, generate timestamps, and enforce approval workflows on the backend.

Principles to apply:

- Declare only fields the client genuinely needs to supply.
- Do not bind inputs directly to persistence entities containing sensitive properties.
- Check permissions on every resource ID passed in.
- Never trust client-sent role, tenant, or owner fields without verification.
- Limit list sizes, string lengths, and nested input depth.
- Do not let input objects serve as a backdoor to modify fields the user is not authorized to edit.
- Apply transactions and consistency checks at the service layer when a mutation updates multiple tables or resources.

Schema validation restricts data shape; authorization and business validation must still be enforced on the server.

## 12. Testing mutations that accept input objects

Spring for GraphQL provides **GraphQlTester** to execute operations and assert results. Example:

~~~java
graphQlTester.document("""
        mutation CreateBook($input: CreateBookInput!) {
            createBook(input: $input) {
                id
                title
                status
            }
        }
        """)
    .variable("input", Map.of(
            "title", "GraphQL with Spring",
            "authorId", "author-01",
            "status", "DRAFT"))
    .execute()
    .path("createBook.title")
    .entity(String.class)
    .isEqualTo("GraphQL with Spring");
~~~

You can test default fields by omitting **status** from variables:

~~~java
graphQlTester.document("""
        mutation CreateBook($input: CreateBookInput!) {
            createBook(input: $input) {
                status
            }
        }
        """)
    .variable("input", Map.of(
            "title", "GraphQL with Spring",
            "authorId", "author-01"))
    .execute()
    .path("createBook.status")
    .entity(String.class)
    .isEqualTo("DRAFT");
~~~

In real tests, services and repositories need to be configured or mocked according to the type of test being written. You can also test:

1. Valid input creates the expected data and returns the output object.
2. Missing **title** or **authorId** is rejected by the schema.
3. Passing an invalid enum is rejected by input coercion.
4. Non-existent fields in an input object are rejected by validation.
5. Values violating Bean Validation are translated into appropriate errors.
6. A non-existent referenced ID produces a business error with a clear code.
7. An unauthorized user cannot create or update another user's resource.
8. Omitted fields and fields passed null behave according to the update contract.
9. Nested inputs and lists bind properly, including empty lists.
10. Multi-step mutations obey transactions and data consistency.

## 13. Common input object design mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using an object type as an input field | Invalid schema | Use scalars, enums, input objects, or IDs |
| Using one input for all mutations | Required fields and edit permissions are unclear | Create separate inputs per use case |
| Exposing an entire entity in an input | Increases mass assignment risk | Accept only fields clients are permitted to change |
| Marking every field non-null | Clients must send unnecessary data | Distinguish create and update inputs |
| Not declaring defaults for stable values | Clients have to repeat default values | Use defaults on input fields or arguments |
| Confusing omitted with null | Patches may unintentionally clear data | Use presence-preserving representations when needed |
| Relying only on GraphQL type validation | Misses business rules | Combine Bean Validation and service validation |
| Not limiting lists or strings | May accept oversized payloads | Restrict size and element counts |
| Trusting client-sent IDs | Risk of cross-tenant or unauthorized resource access | Verify resource permissions on the server |
| Returning internal exceptions to clients | Leaks implementation details | Standardize GraphQL errors and log safely |

## 14. Process for designing an input object for a mutation

When creating a new mutation, you can follow this sequence:

1. Identify the business action and the minimum data the client must provide.
2. Create a dedicated input object for the action, such as **CreateBookInput** or **UpdateBookInput**.
3. Choose scalars, enums, nested input objects, lists, and nullability for each field.
4. Define default values and the meaning of omitting a field.
5. Use IDs for existing resources rather than accepting full output objects.
6. Declare the mutation accepting the input object and returning the appropriate output type.
7. Bind the input into a record/DTO using **@Argument**.
8. Apply schema coercion, Bean Validation, and business validation at the appropriate layers.
9. Check authorization, mass assignment, payload size, and transactions.
10. Write `GraphQlTester` tests for valid, invalid, null, and omitted cases.

Input objects give mutations a concise, strongly typed, and evolvable input contract. In Spring for GraphQL, SDL defines what data is permitted; **@Argument** binds that data into Java objects; validation and the service layer determine whether the data is valid for business rules. Separating these three responsibilities clearly makes mutations easier to read, test, and keep secure as the API grows.
