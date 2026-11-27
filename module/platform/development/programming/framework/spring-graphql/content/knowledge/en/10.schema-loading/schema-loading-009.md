# Schema missing root operation

A GraphQL schema does not just describe object types and data relationships. The schema must also define the root operations that clients are allowed to call. A valid schema always requires a **Query root operation type** to handle data read operations. **Mutation** and **Subscription** are two optional root operation types, only needing to be declared when the API supports writing data or emitting events.

If a schema lacks a Query root, points Query to a nonexistent type, or uses a non-object type as a root, GraphQL cannot build a valid schema. With Spring for GraphQL, the error typically appears when the application initializes the GraphQL runtime, before the endpoint can handle queries. Therefore, when seeing errors related to the query root or schema validation, inspect the SDL and how schema files are merged.

## What is a root operation type?

GraphQL has three operation types that clients can send:

| Operation | Root operation type | Purpose |
| --- | --- | --- |
| Query | Query root | Reading data |
| Mutation | Mutation root | Modifying data or state |
| Subscription | Subscription root | Receiving events over time |

A root operation type is the starting point for GraphQL to execute an operation. When a client sends a query, GraphQL begins resolving the selected fields from the Query root. For mutations, execution starts from the Mutation root; for subscriptions, GraphQL starts from the Subscription root and establishes a data stream over a supported transport.

A minimal schema must have a Query root:

~~~graphql
type Query {
  health: String!
}
~~~

In this example, Query is the root object type and health is a data-reading field. This field can return application health information or the API version. The Query root should not be an empty type: an object type in GraphQL must have at least one field.

Mutation and Subscription are optional. A read-only API can have only Query. An API with mutations must still have Query, even when most of the API's business logic involves writing data. GraphQL does not support a schema with only a Mutation root and no Query root.

## Default root operations by name

If the SDL does not declare an explicit schema block, GraphQL uses root operation names by convention:

- An object type named Query is used as the Query root and is required.
- If an object type named Mutation exists, it is used as the Mutation root.
- If an object type named Subscription exists, it is used as the Subscription root.

For example, the following schema is valid without writing a schema block:

~~~graphql
type Query {
  book(id: ID!): Book
  books: [Book!]!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}

type Book {
  id: ID!
  title: String!
}

input CreateBookInput {
  title: String!
}
~~~

In this schema, GraphQL recognizes Query and Mutation by name. Query is the required root; Mutation is recognized because an object type with that name exists. Without declaring Subscription, the schema remains valid and clients cannot send subscription operations.

A common mistake is declaring only domain data types while forgetting Query:

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

Book and Author are valid object types, yet they do not automatically become root operations. The schema above lacks Query and therefore cannot be used as a complete GraphQL schema. You must add a Query root with at least one field:

~~~graphql
type Query {
  books: [Book!]!
  authors: [Author!]!
}
~~~

## Explicit root operation declaration

When you want to use root names different from the convention, or want to specify root mappings explicitly, declare a schema block:

~~~graphql
schema {
  query: RootQuery
  mutation: RootMutation
}

type RootQuery {
  books: [Book!]!
}

type RootMutation {
  createBook(input: CreateBookInput!): Book!
}

type Book {
  id: ID!
  title: String!
}

input CreateBookInput {
  title: String!
}
~~~

Here RootQuery is the Query root and RootMutation is the Mutation root. Type names do not need to be Query or Mutation because the schema block declares their roles.

When using an explicit schema definition, declare the Query root properly. The following example is invalid because there is no query operation type:

~~~graphql
schema {
  mutation: RootMutation
}

type RootMutation {
  resetCatalog: Boolean!
}
~~~

Having a Mutation root does not replace the Query root requirement. The fix is to add a Query root with a read field:

~~~graphql
schema {
  query: RootQuery
  mutation: RootMutation
}

type RootQuery {
  health: String!
}

type RootMutation {
  resetCatalog: Boolean!
}
~~~

The declared root operation type must exist in the schema and must be an object type. You cannot point query to a scalar, enum, interface, union, or input object. If a root name is declared but its corresponding type is missing, schema validation also fails.

## Distinguishing root operations from regular object types

Not every object type can be called directly by clients. For example:

~~~graphql
type Book {
  id: ID!
  title: String!
  author: Author
}

type Author {
  id: ID!
  name: String!
}
~~~

Book and Author describe data, while Query defines entry fields for clients to begin querying. A client does not send an operation directly against Book; it calls a field on Query and then traverses to Book:

~~~graphql
query {
  book(id: "book-101") {
    id
    title
    author {
      name
    }
  }
}
~~~

The data flow can be visualized as follows:

~~~mermaid
flowchart TD
    A["GraphQL client"] --> B["Query root"]
    B --> C["Field book(id)"]
    C --> D["Object Book"]
    D --> E["Field author"]
    E --> F["Object Author"]
    B --> G["Other Query fields"]
~~~

Root types create controlled entry points for the API. Remaining object types are accessed through fields exposed on the roots or related objects.

## When splitting the schema into multiple files

Large applications often split SDL into multiple files by domain, such as book.graphqls, author.graphqls, and query.graphqls. Spring Boot can load multiple schema files in the configured resource location and combine them into one schema.

Example:

~~~text
src/main/resources/graphql/
├── query.graphqls
├── book.graphqls
└── author.graphqls
~~~

query.graphqls defines the root:

~~~graphql
type Query {
  books: [Book!]!
  authors: [Author!]!
}
~~~

book.graphqls defines the object:

~~~graphql
type Book {
  id: ID!
  title: String!
}
~~~

author.graphqls defines the remaining object:

~~~graphql
type Author {
  id: ID!
  name: String!
}
~~~

In this model, only one file needs to declare the initial type Query. Other files can extend the root using a type extension:

~~~graphql
extend type Query {
  featuredBooks: [Book!]!
}
~~~

The key point is that extend type Query only extends an existing type. It does not create a new Query root. If all files only contain extend type Query without any file defining the base type Query, schema merging will fail because there is no type to extend.

Another organizational approach is placing all root fields in a single query.graphqls file, while domain files only define object types and related fields. Whichever approach you choose, after loading all SDL there must still be a valid Query root.

## Configuring schema loading in Spring for GraphQL

With Spring Boot, the GraphQL starter dependency provides auto-configuration for the schema and runtime. Schemas are usually placed in:

~~~text
src/main/resources/graphql/
~~~

By default, Spring Boot looks for schema files on the classpath at the configured GraphQL location. You can specify another location in application.yml:

~~~yaml
spring:
  graphql:
    schema:
      locations: classpath:graphql/
      file-extensions: .graphqls,.gqls
~~~

During initialization, Spring for GraphQL combines schema resources, builds the GraphQL runtime, and applies runtime wiring configurers. If the SDL lacks a Query root or has an invalid root mapping, building the schema will raise an error. The /graphql endpoint may not be available because the application failed to finish initializing.

Do not try to fix a missing root error by adding a controller with @QueryMapping without adding the corresponding field in SDL. Controller resolvers only map to fields already present in the schema; they do not replace defining the Query root.

## Mapping root operations to Spring Controllers

After the schema declares Query, controllers can map fields using @QueryMapping:

~~~graphql
type Query {
  health: String!
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

~~~java
@Controller
public class BookGraphQlController {

    private final BookService bookService;

    public BookGraphQlController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public String health() {
        return "UP";
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }
}
~~~

The method name is used by default as the field name if no other name is specified. @QueryMapping handles fields belonging to the Query root. Similarly, @MutationMapping maps fields of the Mutation root and @SubscriptionMapping maps fields of the Subscription root.

If the schema declares a custom root such as RootQuery, pay attention to the type name the annotation maps to. @QueryMapping is shorthand for mapping onto the conventional root type named Query. For RootQuery, use @SchemaMapping and specify typeName explicitly:

~~~java
@Controller
public class CustomRootController {

    @SchemaMapping(typeName = "RootQuery", field = "health")
    public String health() {
        return "UP";
    }
}
~~~

The schema definition must still declare query: RootQuery. The annotation only maps a Java method to a field; it does not replace declaring the root operation in SDL.

Example operation:

~~~graphql
query {
  health
  book(id: "book-101") {
    id
    title
  }
}
~~~

A resolver cannot make a schema missing Query valid. Ensure the root type and fields exist first, then check controller mappings.

## Common causes of missing root operation errors

| Cause | Symptom | Resolution |
| --- | --- | --- |
| Missing type Query definition | Schema only has Book, Author, or business objects | Create a Query root with at least one field |
| Custom root name used without schema declaration | RootQuery exists but GraphQL does not recognize it as query root | Add a schema block and map query: RootQuery |
| Schema block omits query | Only mutation or subscription declared | Add a query root |
| Referenced root type does not exist | schema points to a misspelled type or defining file is not loaded | Fix the name or schema file location |
| Root type is not an object | Query points to a scalar, interface, or input type | Use an object type as the root |
| Only extend type Query used | No base type Query definition in loaded files | Create type Query before using extensions |
| Root file not loaded by Spring Boot | SDL has Query but sits outside schema locations | Fix schema locations or resource path |
| Duplicate root definitions | Multiple files declare separate type Query definitions | Keep one base definition and use extend type Query for additions |

## How to diagnose in a Spring application

When the application fails to start with a schema validation error, check in this order:

1. **Check loaded SDL.** Confirm there is a file defining the Query root, not only business object types.
2. **Check the schema block.** If using custom root names, confirm query is mapped to the right object type.
3. **Check resource locations.** Ensure schema files are on the classpath and match the schema locations setting.
4. **Check type extensions.** Do not use extend type Query before a base type Query exists in the merged schema.
5. **Check the root type.** The root must be a valid object type and have at least one field.
6. **Check wiring after the schema is valid.** Once the root is recognized, inspect @QueryMapping and corresponding data fetchers.

Do not handle this by catching the startup exception and continuing to run the application with a schema missing Query. If the schema is invalid, the GraphQL runtime has no entry point to execute queries. The application should fail at startup so configuration errors are caught early.

## Testing a schema with root operations

Include tests that initialize the GraphQL runtime or Spring context integration tests to confirm the schema loads and the Query root exists. You can use GraphQlTester to test real operations once the context starts:

~~~java
graphQlTester.document("""
        query {
            health
        }
        """)
    .execute()
    .path("health")
    .entity(String.class)
    .isEqualTo("UP");
~~~

In addition to success cases, write separate invalid-schema tests to confirm misconfigurations like a missing Query or extending a nonexistent root are caught. These tests prevent regressions when splitting schemas into multiple files or when a team adds a new domain.

## Checklist when adding a new schema

Before finalizing an SDL change, verify:

- There is a Query root operation specified in the merged schema.
- The Query root is declared directly or mapped explicitly in a schema block.
- The Query root is an object type and has at least one field.
- Mutation and Subscription are declared only when the API genuinely needs them.
- All files using extend type Query have a base Query definition in the merged schema.
- Spring Boot loads all schema files from the right classpath locations.
- @QueryMapping methods correspond to real fields in the SDL.
- The application starts successfully and GraphQlTester can execute a basic query.

A schema missing a root operation is a structural error in the GraphQL contract, not a data-query error inside a resolver. The Query root is always mandatory; Mutation and Subscription are optional. In Spring for GraphQL, ensure SDL is completely loaded, roots are properly declared, and controllers only map to fields present in the schema. Checking these points while building the GraphQL runtime helps catch errors early, especially when schemas are split across domains.
