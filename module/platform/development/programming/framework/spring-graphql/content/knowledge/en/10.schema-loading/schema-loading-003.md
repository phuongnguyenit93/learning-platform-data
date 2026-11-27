# schema.graphqls

## Objectives

After this lesson, you can:

- Explain the role of the schema.graphqls file in a Spring for GraphQL application.
- Place SDL files in the right location so Spring Boot automatically discovers and loads the schema.
- Understand how Spring Boot merges multiple GraphQL schema files into a single complete schema.
- Organize schemas by type or business domain using type extensions.
- Recognize common errors when naming, declaring, or loading schemas.
- Test the loaded schema together with resolvers in a Spring Boot application.

## What is schema.graphqls?

schema.graphqls is a commonly used filename for files containing GraphQL Schema Definition Language (SDL). This file describes the GraphQL API contract: root operations, object types, input types, scalars, enums, interfaces, unions, fields, arguments, and nullability.

Spring for GraphQL uses the SDL schema to build the GraphQL schema when the application starts. Annotated controllers such as @QueryMapping, @MutationMapping, and @SchemaMapping provide the handling logic for fields declared in the schema. Controllers do not automatically generate the entire GraphQL contract from Java method names.

A minimal schema.graphqls file can declare:

~~~graphql
type Query {
  bookById(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

In this example:

- Query is the root object type for read operations.
- bookById is a root field that clients can invoke.
- id is a required argument of type ID!.
- Book is the returned object type.
- id and title are fields that clients can select in the selection set.

When a client sends a bookById query, the GraphQL engine validates the operation against the schema and then locates the appropriate resolver to execute the field. If the schema does not declare the field or the types used are invalid, the operation will not pass validation.

## Default location in Spring Boot

With Spring Boot and Spring for GraphQL, the default location to place schema resources is the graphql directory on the classpath. In a Gradle or Maven project, the common structure is:

~~~text
src/
└── main/
    └── resources/
        └── graphql/
            └── schema.graphqls
~~~

When building the application, files in src/main/resources are placed on the classpath. Spring Boot GraphQL auto-configuration searches for schemas in the default location and creates GraphQlSource from the loaded definitions.

The name schema.graphqls is an easily recognizable convention, not the only filename required by the framework. What matters is that the file resides in a configured schema location and has an extension recognized by the loader.

The extensions commonly supported by Spring Boot by default are .graphqls and .graphql. Using .graphqls for SDL files helps readers recognize them as GraphQL schemas. If the project configures a custom list of extensions, ensure the file uses an extension present in that list.

## Configuring schema location

If you keep the default structure, extra configuration is usually unnecessary. When schemas are placed in another location, you can change the schema location using the spring.graphql.schema.locations property.

Example in application.properties when schemas are placed in the api-schema directory:

~~~properties
spring.graphql.schema.locations=classpath:api-schema/**/
~~~

With the default graphql structure and subdirectories by business domain, you can use:

~~~properties
spring.graphql.schema.locations=classpath:graphql/**/
~~~

You can configure recognized file extensions:

~~~properties
spring.graphql.schema.file-extensions=.graphqls,.graphql
~~~

Configuration values must match the Spring Boot version your project uses. Check the configuration metadata for that version if the project overrides the location or extension list. When changing the location, verify that the resources are actually copied to the classpath after building.

If using YAML:

~~~yaml
spring:
  graphql:
    schema:
      locations: classpath:api-schema/**/
      file-extensions:
        - .graphqls
        - .graphql
~~~

Do not confuse schema location with the HTTP endpoint. spring.graphql.schema.locations determines where the server reads SDL on startup; spring.graphql.path determines the HTTP URL that clients call. The two settings serve two different layers.

## Basic contents of schema.graphqls

A schema typically declares root operation types and business domain types. Example library API:

~~~graphql
type Query {
  bookById(id: ID!): Book
  books(first: Int = 20): [Book!]!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}

type Book {
  id: ID!
  title: String!
  pageCount: Int
  author: Author
}

type Author {
  id: ID!
  name: String!
}

input CreateBookInput {
  title: String!
  authorId: ID!
  pageCount: Int
}
~~~

The schema above describes:

- Query fields to retrieve a single book or a list of books.
- A Mutation field to create a book.
- Book and Author object types for responses.
- CreateBookInput input object for data sent by clients.
- Standard scalars ID, String, and Int.
- Nullability and default values for each field and argument.

The schema is a contract independent of storage mechanisms. There is no need to declare database table names or column names in SDL. Controllers and services map this contract to the application's domain model.

## Splitting the schema into multiple files

A small application can keep the entire SDL in schema.graphqls. As the schema grows, keeping every type in one file makes searching harder and increases merge conflicts when multiple people edit it simultaneously.

Spring Boot allows loading multiple schema resources from configured schema locations. For example:

~~~text
src/main/resources/graphql/
├── schema.graphqls
├── book.graphqls
├── author.graphqls
└── order.graphqls
~~~

The files are merged into a single GraphQL schema during initialization. Filenames do not automatically create separate namespaces or modules. Types and fields across files still belong to the same schema, so type names must be consistent and must not be defined redundantly in an invalid way.

One way to organize is keeping root types and shared types in schema.graphqls, then extending each root type in domain files:

~~~graphql
# schema.graphqls
type Query {
  health: String!
}

type Mutation {
  noop: Boolean
}
~~~

~~~graphql
# book.graphqls
type Book {
  id: ID!
  title: String!
}

extend type Query {
  bookById(id: ID!): Book
  books: [Book!]!
}
~~~

~~~graphql
# author.graphqls
type Author {
  id: ID!
  name: String!
}

extend type Query {
  authorById(id: ID!): Author
}
~~~

Type extensions allow adding fields to an already declared type. In the example, Query is defined once in schema.graphqls; book.graphqls and author.graphqls add fields using extend type Query.

Do not redeclare type Query in multiple files as if each file had its own separate root Query. If a type is already defined, use type extensions to add fields. SDL files are merged before the schema is built and validated.

## Rules for organizing multiple files

When splitting a schema, follow a few rules:

1. Each object type or input type should have one primary definition location so the contract source is easy to find.
2. Root types Query, Mutation, and Subscription should have a clear base definition.
3. Domain files use extend type to add fields to root types or shared types.
4. Do not create two independent definitions with the same name for a single type.
5. Type, field, argument, and enum names must be consistent across files.
6. Place custom scalars in a shared file and ensure runtime wiring registers the corresponding scalars.
7. Use subdirectories by domain if the schema location pattern can recursively discover those resources.

Example of a larger structure:

~~~text
src/main/resources/graphql/
├── schema.graphqls
├── common/
│   ├── scalars.graphqls
│   └── pagination.graphqls
├── catalog/
│   ├── book.graphqls
│   └── author.graphqls
└── sales/
    ├── order.graphqls
    └── customer.graphqls
~~~

Directories only help organize resources. They do not create security boundaries or independent GraphQL modules. Every file discovered via schema locations contributes to the same runtime schema.

## Root operation types and schema declaration

GraphQL uses the default names Query, Mutation, and Subscription for root operation types. When using those exact default names, the schema usually does not need an explicit schema block declaration.

~~~graphql
type Query {
  books: [Book!]!
}
~~~

If you want to use different root type names, you must declare a schema definition:

~~~graphql
schema {
  query: ReadOperations
  mutation: WriteOperations
}

type ReadOperations {
  books: [Book!]!
}

type WriteOperations {
  createBook(input: CreateBookInput!): Book!
}
~~~

Do not rename root types just because you want to name a Java controller differently. Root types are part of the schema contract; if changed, clients and related schema files must be updated in sync.

## Linking the schema to annotated controllers

After SDL is loaded, Spring for GraphQL links fields to controller methods via annotation mapping.

With the schema:

~~~graphql
type Query {
  bookById(id: ID!): Book
}
~~~

The controller can be written as:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book bookById(@Argument("id") String id) {
        return bookService.findById(id).orElse(null);
    }
}
~~~

The method name bookById is used as the default field name on Query. @QueryMapping is a shortcut for mapping onto the root Query type. If the method or field has a different name, you can specify the name explicitly in the annotation.

Points to remember:

- SDL declares the bookById field and the id argument.
- @QueryMapping provides the resolver for that field.
- @Argument binds the id value from the request to the Java parameter.
- Book is the response type; GraphQL continues resolving the fields selected by the client.

If a controller has a mapping for a field that does not exist in the schema, having the Java method does not automatically make that field appear in the GraphQL API. Conversely, a field declared in the schema without a matching resolver or property data fetcher may return null or cause an error depending on nullability.

## Custom scalars require both declaration and runtime wiring

Declaring a scalar in SDL specifies the type name in the contract:

~~~graphql
scalar DateTime

type Event {
  id: ID!
  startsAt: DateTime!
}
~~~

The server must also register an implementation for that scalar. Example using an extended scalar:

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

If SDL declares DateTime but runtime wiring does not register the corresponding scalar, the schema may fail to build or fail to handle data types as expected. The scalar name in SDL and the registered scalar name must match.

## Checking the schema at application startup

Spring for GraphQL builds the GraphQL schema from SDL resources during application context initialization. Syntax errors, invalid types, fields referencing undeclared types, or incomplete interface implementations can prevent the application from starting.

When encountering schema loading errors:

- Check whether the file is under resources/graphql or the configured schema location.
- Check whether the extension is included in spring.graphql.schema.file-extensions.
- Check whether the file was copied to the classpath after building.
- Check SDL syntax, braces, colons, referenced types, and nullability.
- Check whether type extensions have an existing target type.
- Check whether all object types implementing an interface provide the required fields.
- Check whether custom scalars have been registered in runtime wiring.

Some errors only appear when building the schema, before the HTTP server accepts requests. Therefore, read the startup logs and root exception rather than only testing the /graphql URL.

## Testing the loaded schema

GraphQlTester allows executing operations against the GraphQL runtime in tests. With Spring Boot, you can use @GraphQlTest to create a test slice for GraphQL controllers and required configuration, or use an integration test with the full application context when you want to verify actual schema resource loading.

Example testing a query:

~~~java
graphQlTester.document("""
        query BookById($id: ID!) {
            bookById(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "book-101")
    .execute()
    .path("bookById.title")
    .entity(String.class)
    .isEqualTo("Spring GraphQL Guide");
~~~

When testing schema loading, include at least one integration test that initializes the application context from real resources. That test helps catch cases where an SDL file is placed in the wrong directory, has the wrong extension, or is omitted from the build artifact.

In addition to successful operations, check:

1. Fields in the schema have corresponding mappings.
2. Arguments bind with the right types.
3. Fields extended from other SDL files still appear in the final schema.
4. Interfaces, unions, enums, and custom scalars are registered properly.
5. An invalid schema causes context initialization to fail with clear diagnostic information.

## Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Application cannot find schema | File is outside default classpath location | Place in src/main/resources/graphql or configure schema locations |
| Schema file is ignored | Extension is not in the file extensions list | Use .graphqls/.graphql or update configuration |
| Query field does not exist | Field not declared or file containing field not loaded | Check SDL and schema locations |
| Duplicate type definition | Multiple files redeclare the same type instead of using extensions | Keep one type definition and use extend type |
| Invalid type extension | Target type not declared yet or duplicate field | Check base type and field names |
| Resolver is not invoked | Mapping name does not match schema or controller not scanned | Check annotations and component scan |
| Custom scalar does not work | Scalar declared only in SDL without runtime wiring registration | Add RuntimeWiringConfigurer |
| Application fails to start | Invalid SDL syntax or schema validation failure | Read root exception and inspect merged schema files |

## Comprehensive practice

Create a Spring Boot application with Spring for GraphQL and build a multi-file library schema:

1. Create src/main/resources/graphql/schema.graphqls containing root Query and Mutation.
2. Create book.graphqls containing Book, CreateBookInput, and extend type Query.
3. Create author.graphqls containing Author and extend type Query.
4. Write @QueryMapping methods for bookById and authorById.
5. Run the application and send queries to the GraphQL endpoint to verify data.
6. Change the schema location to another directory, update the configuration, and verify the files are loaded.
7. Try declaring a duplicate type or omitting a required field to observe schema loading errors.
8. Write an integration test confirming that SDL files are merged into a complete schema.

After completing this, explain why the filename schema.graphqls is just a convention, why multiple files still form a single schema, and when to use extend type instead of declaring a type again.

## Key takeaways

schema.graphqls is a conventional name for a GraphQL SDL file. Spring Boot usually discovers schemas automatically in classpath:graphql/**/ with supported extensions such as .graphqls and .graphql. You can split schemas into multiple files by business domain; the loader merges them into one shared schema. When adding fields to an existing type, use extend type instead of redefining the type. SDL is the API contract, while annotated controllers and runtime wiring provide resolvers and scalar implementations. Always validate the schema at startup and include an integration test confirming resources are actually loaded.
