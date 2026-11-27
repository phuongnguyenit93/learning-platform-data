# GraphQL Type System

The GraphQL type system defines the data that a GraphQL API can accept and return. The schema describes what types exist, the fields on each type, input arguments, result types, and the relationships clients are permitted to query. Every client operation is validated against the schema before resolvers execute.

In Spring for GraphQL, schemas are typically declared using **Schema Definition Language (SDL)** in **.graphqls** or **.gqls** files. Spring GraphQL pairs this schema with Java methods registered as data fetchers, such as via **@QueryMapping**, **@MutationMapping**, and **@SchemaMapping**. It helps to separate the two parts: the GraphQL type system defines the API contract; Java code supplies the data to fulfill that contract.

After this lesson, you will be able to read and design a schema containing root types, scalars, objects, enums, input objects, interfaces, unions, lists, and non-nulls; know which types are allowed in input versus output positions; and understand how Spring for GraphQL wires schemas to resolvers.

## 1. The type system is the contract between client and server

A GraphQL server does not expose all internal classes, entities, or database tables directly. Instead, the server exposes a well-structured schema. Clients may only select fields declared in the schema and must pass arguments of the correct types.

For example, if the schema declares:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

The client can request **book**, pass a required **ID**, and select the **id** and **title** fields on the result. The client cannot arbitrarily request a field named **internalCost** if that field does not exist in the schema. Likewise, the server cannot return an arbitrary value shape that ignores the declared type rules.

A schema provides three important benefits:

- **Discoverability:** clients and developer tooling can inspect what types, fields, arguments, and descriptions the API supports.
- **Operation validation:** field names, arguments, variables, and return types are validated before resolvers run.
- **Stable contract:** the backend can change how data is stored or fetched without necessarily altering the public schema.

The type system does not replace business validation. For instance, the schema can ensure **quantity** is an integer, while whether that quantity exceeds available stock or whether the user is permitted to place an order still must be enforced in the business layer.

## 2. Declaring a schema with SDL

SDL is the text syntax used to describe a schema. A type declaration typically looks like:

~~~graphql
type TypeName {
  fieldName: FieldType
  anotherField(argument: ArgumentType): ReturnType
}
~~~

Type names are case-sensitive. By common convention, type names use PascalCase, while field and argument names use camelCase. Every field has a return type; a field may accept zero or more arguments.

### Root operation types

GraphQL has three types of operations:

| Operation | Root type | Purpose |
|---|---|---|
| Query | **Query** | Read data |
| Mutation | **Mutation** | Perform data modifications |
| Subscription | **Subscription** | Receive events or updates over time |

A schema must have a Query root. Mutation and Subscription are optional. If the default names **Query**, **Mutation**, and **Subscription** are used, an explicit **schema** block can be omitted. If you want to use different root type names, declare it explicitly:

~~~graphql
schema {
  query: ReadOperations
  mutation: WriteOperations
}

type ReadOperations {
  health: String!
}

type WriteOperations {
  refreshCache: Boolean!
}
~~~

With Spring Boot and Spring for GraphQL, schemas are typically placed in **src/main/resources/graphql/**, such as **schema.graphqls** or **books.graphqls**. Spring Boot automatically discovers schema files in the default configured locations and merges the definitions. You can split schemas by business area; when you need to add fields to an already declared type, SDL supports the **extend type** syntax.

For example, one file can define **type Query**, while another file adds:

~~~graphql
extend type Query {
  recentBooks(limit: Int = 10): [Book!]!
}
~~~

All files still form a single unified schema. A type name is defined in one place; extensions must reference an existing type accurately.

## 3. Named type categories

GraphQL has six main categories of named types: scalar, object, enum, input object, interface, and union. Each has a distinct purpose and valid usage positions.

### Scalar: single atomic values

Scalars represent atomic values. GraphQL defines five built-in scalars:

| Scalar | Meaning |
|---|---|
| **Int** | Signed 32-bit integer |
| **Float** | Floating-point number |
| **String** | Character string |
| **Boolean** | True or false value |
| **ID** | Identifier; typically serialized as a string |

**ID** is intended for identifiers and does not imply the underlying data type of a database primary key. An ID can be a UUID, a business code, or a server-managed opaque value. Do not use **Int** for identifiers just because the current primary key is numeric.

GraphQL does not include built-in types such as **Date**, **DateTime**, **Decimal**, **Long**, or **UUID**. When an API needs them, declare custom scalars:

~~~graphql
scalar DateTime
scalar Money
~~~

Declaring **scalar** in SDL only names the type in the schema. The server must also provide runtime conversion and validation for its values. Integration with Spring for GraphQL is covered in section 8.

### Object type: output data structures

An object type describes an object with fields. Example:

~~~graphql
type Book {
  id: ID!
  title: String!
  publishedAt: DateTime
}
~~~

An object type can contain scalar fields, enum fields, or fields referencing other objects, interfaces, or unions. Reference fields form relationships that can be queried in a nested manner:

~~~graphql
type Book {
  id: ID!
  title: String!
  author: Author!
}

type Author {
  id: ID!
  name: String!
}
~~~

Clients can fetch both the book and its author in a single operation:

~~~graphql
query {
  book(id: "book-01") {
    title
    author {
      id
      name
    }
  }
}
~~~

Relationships in the schema only describe the API shape. They do not automatically create database relationships, nor do they guarantee efficient data retrieval. The resolver for **author** still has to be executed or supplied by a property data fetcher.

Fields can also take arguments. This allows expressing filters or query parameters right where the field is used:

~~~graphql
type Query {
  books(status: BookStatus, limit: Int = 20): [Book!]!
}
~~~

### Enum: finite set of values

Enums restrict the value of a field or argument to a predefined set of named values:

~~~graphql
enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

type Book {
  id: ID!
  status: BookStatus!
}
~~~

Enums fit finite, well-defined sets of choices such as order statuses, roles, or shipping methods. They help clients catch typos and provide stronger type safety than using **String** for everything.

Enum values in operations are written as enum literals without quotes:

~~~graphql
query {
  books(status: PUBLISHED) {
    id
    title
  }
}
~~~

When passed via JSON variables, enum values are represented as matching strings, such as **{"status":"PUBLISHED"}**. Adding a new enum value can affect clients that handle enums exhaustively, so consider backwards compatibility when extending enums.

### Input object: input data structures

Input objects group multiple input values into a single structure. They are commonly used for mutation arguments:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
  status: BookStatus = DRAFT
  publishedAt: DateTime
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

Clients pass input objects via variables:

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
  createBook(input: $input) {
    id
    title
    status
  }
}
~~~

Variables:

~~~json
{
  "input": {
    "title": "GraphQL with Spring",
    "authorId": "author-01",
    "status": "DRAFT"
  }
}
~~~

An input object can contain scalars, enums, other input objects, and wrappers like list/non-null. It cannot contain object types, interfaces, or unions. GraphQL cleanly separates data clients are allowed to send from data the server returns; therefore, a regular object type cannot be used as an input type for a mutation.

Do not default to reusing one input object across all update operations. For instance, **CreateBookInput** and **UpdateBookInput** usually have different required-field rules. Separating them helps the schema express the exact intent of each operation.

### Interface: shared field contract

An interface defines fields that multiple object types commit to providing:

~~~graphql
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
~~~

When a field returns **Node**, clients can query fields declared on the interface, such as **id**. To fetch fields specific to a concrete type, clients use inline fragments:

~~~graphql
query {
  node(id: "item-01") {
    id
    __typename
    ... on Book {
      title
    }
    ... on Author {
      name
    }
  }
}
~~~

An object implementing an interface must provide all fields required by the interface with compatible types according to GraphQL rules. Interfaces are useful when multiple types share a common capability or shared attributes while still keeping specialized fields.

### Union: one of several object types

A union represents a result that can be one of several object types, without requiring those objects to share common fields:

~~~graphql
union SearchResult = Book | Author

type Query {
  search(term: String!): [SearchResult!]!
}
~~~

Because a union declares no shared fields, clients must use inline fragments to select fields on each member type:

~~~graphql
query Search($term: String!) {
  search(term: $term) {
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

Unions only list object types as members. If the result types genuinely share common fields that should be queried directly, an interface may fit better. If they are simply heterogeneous results within the same use case, a union usually expresses intent clearly.

## 4. Input types and output types

A common design mistake is accidentally using an object type in an input position or using an input object as a return type. GraphQL categorizes types by data direction:

| Position in schema | Allowed types |
|---|---|
| Output: field return type | Scalar, enum, object, interface, union |
| Input: argument or input variable | Scalar, enum, input object |

List and non-null wrappers can wrap a valid type on either side. For example:

- **Book** is an output type; it can be a field's return type.
- **CreateBookInput** is an input type; it can be an argument's type.
- **[ID!]!** is a valid input type because it wraps the **ID** scalar.
- **[Book!]!** is a valid output type because it wraps the **Book** object.

The following schema is invalid because it uses an object type as an input:

~~~graphql
type Query {
  findBook(filter: Book): Book
}
~~~

If you need to send filter criteria, define an input object:

~~~graphql
input BookFilter {
  titleContains: String
  status: BookStatus
}

type Query {
  findBooks(filter: BookFilter): [Book!]!
}
~~~

Similarly, do not declare a field returning **CreateBookInput**; return an object type representing the data clients are allowed to read.

## 5. List and Non-Null: understanding nullability accurately

GraphQL provides two wrapper types:

- List **[...]** represents a list.
- Non-Null **!** asserts that the value at that position must never be **null**.

The two wrappers can be combined, and the wrapping order changes the meaning:

| Declaration | Can the list be null? | Can an element be null? |
|---|---:|---:|
| **[Book]** | Yes | Yes |
| **[Book]!** | No | Yes |
| **[Book!]** | Yes | No |
| **[Book!]!** | No | No |

For scalars, **String** can be **null**, while **String!** must always have a value:

~~~graphql
type Profile {
  displayName: String!
  biography: String
}
~~~

Here **displayName** is required to have a value; **biography** may be absent or unprovided and returned as **null**. The **!** mark does not mean the client is required to select the field in a query. It is a guarantee on the value returned by the server, or on the input value required by the schema.

### Non-null on inputs

With argument **id: ID!**, the client must provide the argument and its value cannot be **null**:

~~~graphql
type Query {
  book(id: ID!): Book
}
~~~

If the argument is missing or **null** is passed, the operation is invalid against the schema. An argument with a default value can be omitted by the client:

~~~graphql
type Query {
  books(limit: Int = 20): [Book!]!
}
~~~

If the client omits **limit**, the server uses the default value **20**. For input objects, fields can be marked non-null or given default values following the same rules.

### Non-null on outputs and null propagation

When a resolver returns **null** for a non-null field, GraphQL produces an execution error and propagates **null** up to the nearest nullable parent field. This process is commonly called null propagation or null bubbling.

Example:

~~~graphql
type Book {
  id: ID!
  author: Author!
}

type Query {
  book(id: ID!): Book
}
~~~

If the **Book.author** resolver returns **null**, the **author** field violates the **Author!** contract. GraphQL must turn the parent **Book** into **null**. Because **Query.book** allows null, the final result may be **book: null** accompanied by an error in the **errors** array.

If the **book** field itself is declared **Book!**, the error propagates further up to the root result. With a list **[Book!]!**, an element cannot be null; if one element violates this, the entire list becomes null, and since the list is also non-null, the error propagates up to the parent.

Therefore, choosing non-null is a design decision that impacts response resilience. Only use **!** when the server can truly guarantee a value in every valid scenario. A field that depends on an external service or potentially missing data may need to be nullable, depending on the business contract.

## 6. Complete schema example

The following example combines the common type categories found in a book management API:

~~~graphql
scalar DateTime

enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

interface Node {
  id: ID!
}

type Book implements Node {
  id: ID!
  title: String!
  status: BookStatus!
  publishedAt: DateTime
  author: Author!
  tags: [String!]!
  legacyCode: String @deprecated(reason: "Use id")
}

type Author implements Node {
  id: ID!
  name: String!
  books: [Book!]!
}

union SearchResult = Book | Author

input CreateBookInput {
  title: String!
  authorId: ID!
  status: BookStatus = DRAFT
  publishedAt: DateTime
}

type Query {
  book(id: ID!): Book
  node(id: ID!): Node
  books(status: BookStatus, limit: Int = 20): [Book!]!
  search(term: String!): [SearchResult!]!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

This schema reflects several design decisions:

- **Query.book** returns a nullable **Book** because the book ID may not exist.
- **Query.books** returns a non-null list, and each element is also non-null. A successful query must produce a list; each item must be a **Book**.
- **Book.author** is non-null, meaning every returned book must have a valid author per the API contract.
- **publishedAt** is nullable because a draft book may not have a publication date yet.
- **CreateBookInput** uses **authorId** so clients specify the author; the server decides how to load and associate the author.
- **SearchResult** allows search results to be either books or authors.
- **legacyCode** is marked deprecated to signal clients to switch to **id**.

A query using the interface and union can be written as:

~~~graphql
query SearchCatalog($term: String!, $id: ID!) {
  node(id: $id) {
    id
    __typename
    ... on Book {
      title
      status
    }
    ... on Author {
      name
    }
  }
  search(term: $term) {
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

**__typename** is a meta-field provided by GraphQL that returns the concrete object type name at runtime. It is useful when clients need to distinguish result types, especially with interfaces and unions.

## 7. How GraphQL validates operations

Suppose the schema has the field:

~~~graphql
type Query {
  book(id: ID!): Book
}
~~~

The following operation is type-valid:

~~~graphql
query FindBook($id: ID!) {
  book(id: $id) {
    id
    title
  }
}
~~~

The following operation is invalid because **Book** does not declare a **name** field:

~~~graphql
query FindBook($id: ID!) {
  book(id: $id) {
    name
  }
}
~~~

The following operation is also invalid because the **id** variable has nullable type **ID**, while the argument requires **ID!**:

~~~graphql
query FindBook($id: ID) {
  book(id: $id) {
    id
  }
}
~~~

These errors are caught during the validation phase, before resolvers fetch any data. When designing a schema, treat validation errors as part of the contract: they help clients catch invalid API calls early.

## 8. Connecting the type system to Spring for GraphQL

In Spring for GraphQL, SDL describes the fields and data types; controllers supply the logic to fetch values for those fields. For example, given this schema snippet:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  author: Author!
}
~~~

A controller can implement the root field and the relationship field:

~~~java
@Controller
public class BookGraphQlController {

    private final BookService bookService;
    private final AuthorService authorService;

    public BookGraphQlController(
            BookService bookService,
            AuthorService authorService) {
        this.bookService = bookService;
        this.authorService = authorService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }
}
~~~

**@QueryMapping** maps the **book** method to the **Query.book** field. **@Argument** extracts the **id** argument from the operation. **@SchemaMapping** maps the **author** method to the **Book.author** field; the **Book** parameter is the source object for which the field is being resolved.

Java class names do not automatically define GraphQL types. **Book** in SDL is the schema type name; **Book** in the method parameter is the Java type received by the resolver. Both sides must be mapped consistently, though the Java model does not have to mirror the schema structure identically. If the source object already exposes a matching property, GraphQL Java can read that property using the default property data fetcher without writing a separate resolver.

Remaining root fields are mapped similarly with **@MutationMapping** and **@SubscriptionMapping**. For relationship fields invoked across many objects, a naive resolver can cause many data queries. **@BatchMapping** or DataLoader are mechanisms to batch data loads, helping address the N+1 problem; that is an optimization at the execution layer, while the schema preserves the exact same type contract.

### Registering custom scalars

For **DateTime** in the schema example, the server needs a scalar implementation to convert between GraphQL values and Java types. You can use the GraphQL Java Extended Scalars library and register the scalar via **RuntimeWiringConfigurer**. After adding the corresponding dependency, the configuration can look like:

~~~java
@Configuration
public class GraphQlScalarConfiguration {

    @Bean
    RuntimeWiringConfigurer runtimeWiringConfigurer() {
        return wiringBuilder ->
                wiringBuilder.scalar(ExtendedScalars.DateTime);
    }
}
~~~

**scalar DateTime** in SDL and **ExtendedScalars.DateTime** in runtime wiring must share the same name. The scalar implementation is responsible for serializing return values and parsing input values from variables or literals. If you need a system-specific date/time format, you can build a **GraphQLScalarType** with an appropriate **Coercing**, while also validating malformed inputs and timezone rules.

### Resolving interfaces and unions

When a resolver returns a field typed as an interface or union, GraphQL needs to know the concrete object type of each value at runtime. For example, **SearchResult** may receive a Java **Book** or **Author** object. GraphQL Java uses a **TypeResolver** to determine the corresponding object type.

If the default resolution mechanism does not recognize the application's Java types, register a type resolver via **RuntimeWiringConfigurer** for the corresponding interface or union. The resolver must return the exact GraphQL object type declared in SDL. Declaring **union SearchResult = Book | Author** only describes the valid members; it does not determine which member a specific Java object belongs to.

## 9. Directives and introspection

Directives attach extra instructions to a schema or operation. GraphQL has common built-in directives:

| Directive | Purpose |
|---|---|
| **@skip(if: Boolean!)** | Skips a field or fragment when the condition is true |
| **@include(if: Boolean!)** | Includes a field or fragment in the response only when the condition is true |
| **@deprecated(reason: String)** | Marks a field or enum value as obsolete |
| **@specifiedBy(url: String!)** | Links a specification URL to a custom scalar |

Example of marking an old field:

~~~graphql
type Book {
  id: ID!
  legacyCode: String @deprecated(reason: "Use id")
}
~~~

Clients can still query the deprecated field during a transition period, while schema tooling can display warnings to encourage migrating to the new field.

GraphQL also provides introspection so clients or tools can explore the schema. **__schema** and **__type** let you query metadata about the schema; **__typename** reveals the concrete object type of a value. Introspection helps IDEs and client generators understand the API without reading server source code.

Directives do not replace authorization. For example, hiding a field from documentation or skipping a field on the client does not guarantee a user cannot invoke that field. Access permissions must be enforced on the server, in resolvers or the appropriate security layer.

## 10. Evolving schemas safely

Because the schema is a public contract, type changes can affect active clients. Several practical guidelines:

- **Prefer backwards-compatible additions:** adding a nullable field is usually less disruptive than adding a required non-null field.
- **Be cautious when adding required arguments:** existing clients that do not pass the new argument may no longer be able to execute the operation.
- **Do not remove fields immediately:** mark them **@deprecated**, state the reason, and give clients time to migrate before removing them.
- **Consider impact when adding enum values:** clients may use exhaustive switches or assume only the older set of values exists.
- **Do not expose persistence structures mechanically:** the schema should reflect client needs and domain language, not necessarily mirror entities or tables.
- **Align nullability with data guarantees:** changing from nullable to non-null or vice versa can change client behavior and how errors propagate.

For example, if the schema previously had:

~~~graphql
type Book {
  id: ID!
  subtitle: String
}
~~~

Adding a new nullable field usually allows older clients to keep working:

~~~graphql
type Book {
  id: ID!
  subtitle: String
  language: String
}
~~~

Meanwhile, adding **language: String!** forces every execution path returning **Book** to supply a value. If older data lacks a language or the resolver cannot determine it, the new field can cause runtime errors and null propagation.

## 11. Common design mistakes

| Issue | Cause | Solution |
|---|---|---|
| Using **type** as an argument | Object types are output types | Declare a separate **input** |
| Using an input object as a return type | Input objects are only for input data | Return an object type |
| Marking every field non-null | Missing data or dependency failures were not evaluated | Choose nullability based on business guarantees |
| Using **String** for all choices | Value set is unconstrained | Use an enum when the value set is finite |
| Declaring a custom scalar without runtime wiring | SDL only declares the scalar name | Register the scalar implementation |
| Returning an interface/union without resolving the concrete type | Runtime does not know the concrete object type | Configure a **TypeResolver** |
| Relationship field runs a query per object | Resolver loads data individually | Consider **@BatchMapping** or DataLoader |
| Adding a non-null field without guaranteed data | Schema promises more than the system can uphold | Backfill data/logic or design it as nullable appropriately |

## 12. Workflow for reading and designing a schema

When reading an existing schema or designing a new one, you can follow this sequence:

1. Identify the root Query, Mutation, and Subscription types to understand the API entry points.
2. Trace the object types returned from root fields to see the data structure clients can read.
3. Distinguish scalars, enums, interfaces, and unions to understand what kinds of values can appear.
4. Inspect input objects and arguments to see what data clients must send.
5. Carefully examine every **!** mark and list bracket pair to determine where null can occur.
6. Look for custom scalars and directives to identify additional rules.
7. Cross-reference fields with Spring GraphQL resolvers to see how data is fetched and how concrete types are resolved.
8. Test sample operations using **GraphQlTester** or appropriate GraphQL tooling to catch schema and validation errors.

A well-designed schema expresses the data clients need, constrains valid inputs, and makes nullability guarantees the server can uphold. In Spring for GraphQL, once you master the type system, writing resolvers becomes much clearer: each method serves a field or group of fields with a concrete contract, while business logic and data-loading strategies are implemented on the server.
