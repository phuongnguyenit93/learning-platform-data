# Schema parse error

Spring for GraphQL needs to load the SDL schema to build the GraphQL runtime before handling client operations. If the schema has syntax errors, invalid type declarations, or missing schema resources, the application may fail to start. When encountering a “schema parse error” message, you need to determine whether the error occurred during file discovery, syntax parsing, schema validation, or resolver configuration.

These four error groups have different timings and fixes. This lesson focuses on how Spring Boot loads schemas, common reasons why a schema fails to build, how to read error messages, and a diagnostic workflow in a Spring for GraphQL application.

## 1. When is the schema loaded?

In a Spring Boot application, Spring for GraphQL builds the GraphQL runtime from the SDL schema and execution configuration. Under Spring Boot's default configuration, schemas are usually searched on the classpath under the graphql/ directory, including subdirectories. Schema files typically use .graphqls or .gqls extensions.

Example resource structure:

~~~text
src/
└── main/
    └── resources/
        └── graphql/
            ├── schema.graphqls
            ├── book.graphqls
            └── author/
                └── author.graphqls
~~~

Spring Boot collects the configured schema resources, and then Spring for GraphQL and GraphQL Java parse, merge, and build the executable schema. The application typically completes this step during ApplicationContext initialization.

High-level flow:

~~~mermaid
flowchart TD
    A["Spring Boot starts"] --> B["Find SDL resources via schema locations"]
    B --> C{"Schema files found?"}
    C -->|No| D["Check classpath and locations configuration"]
    C -->|Yes| E["Read and parse SDL"]
    E --> F{"Valid syntax?"}
    F -->|No| G["Parse error"]
    F -->|Yes| H["Build and validate GraphQL schema"]
    H --> I{"Valid schema?"}
    I -->|No| J["Schema validation / generation error"]
    I -->|Yes| K["Apply runtime wiring"]
    K --> L["GraphQL runtime ready"]
~~~

If an error occurs while building the GraphQL runtime, Spring may report the failure during startup and the ApplicationContext will not be created successfully. Therefore, an SDL error typically surfaces even before any client sends a GraphQL request.

## 2. Distinguishing parse errors from related errors

In practice, any error during schema loading is sometimes broadly called a “schema parse error”. However, you should distinguish the stages:

| Stage | What does it check? | Example error |
| --- | --- | --- |
| Resource discovery | Are SDL files on the right classpath and configured to load? | Schema not found or files in subdirectories omitted. |
| SDL parsing | Is the GraphQL SDL syntax valid? | Missing braces, missing colons, malformed field declarations. |
| Schema validation/generation | Are types and relationships in the schema valid? | Nonexistent type, input type used as output type, duplicate definitions. |
| Runtime wiring | Are execution components configured compatibly? | Custom scalar lacks an implementation or incompatible wiring. |
| Request validation | Is the client-sent operation valid against the loaded schema? | Client requests a nonexistent field or omits a selection set. |
| Field execution | Does the resolver execute successfully? | Repository throws an exception or service finds no data. |

A parse error in the narrow sense is a syntax error when the GraphQL parser reads SDL. If the parser can read the file but the schema cannot be built, that is a validation or schema generation error. If the application has already started and an operation is rejected, that is usually a request validation or execution error.

Distinguishing the stage properly helps avoid editing controllers when the actual issue is in SDL, or altering the schema when the client's request is what is invalid.

## 3. Common SDL syntax errors

SDL has its own syntax. A field is normally declared in the form:

~~~graphql
type Book {
    id: ID!
    title: String!
}
~~~

The field name comes before the colon, and the data type comes after. Some common errors:

**Missing colon after field name**

~~~graphql
type Book {
    id ID!
    title: String!
}
~~~

Fix:

~~~graphql
type Book {
    id: ID!
    title: String!
}
~~~

**Missing closing brace for a type**

~~~graphql
type Book {
    id: ID!
    title: String!
~~~

Fix by properly closing the block:

~~~graphql
type Book {
    id: ID!
    title: String!
}
~~~

**Malformed argument declaration**

~~~graphql
type Query {
    book id: ID!: Book
}
~~~

Correct syntax:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

**Invalid enum value format**

~~~graphql
enum BookStatus {
    IN-PROGRESS
    COMPLETED
}
~~~

Enum value names cannot contain hyphens as normal identifiers. Use the uppercase and underscore convention:

~~~graphql
enum BookStatus {
    IN_PROGRESS
    COMPLETED
}
~~~

When the parser reports a line and column number, start reading around that position. The actual mistake sometimes lies on the preceding line: an unclosed brace or missing colon can cause the parser to detect invalid syntax only at the next token.

## 4. Nonexistent types or wrong type kinds

A schema can be syntactically valid yet invalid because it references an undeclared type.

Example of a typo in a type name:

~~~graphql
type Query {
    book(id: ID!): Bok
}
~~~

If the schema has no Bok type, building the schema fails. Fix it to the correct name:

~~~graphql
type Book {
    id: ID!
    title: String!
}

type Query {
    book(id: ID!): Book
}
~~~

GraphQL also distinguishes input types and output types. An output object cannot be used as an argument:

~~~graphql
type BookFilter {
    keyword: String
}

type Query {
    books(filter: BookFilter): [Book!]!
}
~~~

Because BookFilter is declared with type, it is an output object type. Change it to an input object:

~~~graphql
input BookFilter {
    keyword: String
}

type Book {
    id: ID!
    title: String!
}

type Query {
    books(filter: BookFilter): [Book!]!
}
~~~

The reverse is also invalid: an input object cannot serve as a field's return type. Output fields must return a scalar, enum, object, interface, union, or valid list of output types.

When investigating type errors, check both the base definition and where the type is referenced. The type name may reside in another SDL file, so also confirm that file has been loaded.

## 5. Duplicate definitions and improper type extensions

An application can split a schema into multiple files by domain. When multiple files define types, avoid duplicate declarations.

For example, book.graphqls:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

author.graphqls also declares:

~~~graphql
type Query {
    author(id: ID!): Author
}
~~~

Both files define type Query. When resources are merged, GraphQL does not treat these as two parts of a single type definition. Use extend type Query in the additional file:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

~~~graphql
extend type Query {
    author(id: ID!): Author
}
~~~

The file containing extend type Query must be loaded alongside the schema containing the base Query definition. If the base file is omitted, the extension may reference a nonexistent type.

In addition to duplicate types, avoid:

- Declaring two fields with the same name in the same object type.
- Declaring duplicate arguments on the same field.
- Declaring duplicate enum values.
- Defining the same type in multiple files instead of extending properly.

When splitting a schema into multiple files, clearly assign which file declares the base type and which files only extend types. This reduces conflicts when multiple people develop the schema together.

## 6. Invalid root operation types

A GraphQL schema needs a query root that is an object type. By default convention, if no separate schema definition is declared, the root query type is named Query.

Valid example:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

If using a different name, explicitly declare the root operation:

~~~graphql
schema {
    query: CatalogQuery
}

type CatalogQuery {
    book(id: ID!): Book
}
~~~

Possible errors include:

- Missing query root.
- Root query pointing to a nonexistent type.
- Root query pointing to a scalar, enum, or input object instead of an object type.
- Root operation name in the schema definition not matching the declared type.

Mutation and Subscription are optional. If the application has mutations, declare the root Mutation type and configure matching mappings. If it has subscriptions, declare Subscription and configure a streaming-capable transport. There is no need to declare these root types if the API does not provide the corresponding operations yet.

## 7. Type relationship errors and schema validation rules

GraphQL enforces many rules beyond syntax. For example, a type implementing an interface must provide the required fields with compatible types.

~~~graphql
interface Node {
    id: ID!
}

type Book implements Node {
    title: String!
}
~~~

The schema above is invalid because Book lacks the id field required by the Node interface.

Fix:

~~~graphql
interface Node {
    id: ID!
}

type Book implements Node {
    id: ID!
    title: String!
}
~~~

Unions may also only contain valid object types:

~~~graphql
union SearchResult = Book | Author
~~~

If a member is undeclared or is not an object type, the schema cannot be built properly.

A less common case is a mandatory cycle of input objects. For example:

~~~graphql
input AInput {
    next: BInput!
}

input BInput {
    previous: AInput!
}
~~~

The two input objects require each other via single non-null fields. There is no way to construct a finite value for one input object without a value for the other. You can break the mandatory cycle by allowing null or using a list:

~~~graphql
input AInput {
    next: BInput
}

input BInput {
    previous: AInput
}
~~~

When schema generation reports a validation error even though syntax looks right, check interface implementations, union members, input/output type positions, root operations, and input object cycles.

## 8. Schema not found or incompletely loaded in Spring Boot

A syntactically valid SDL has no effect if the file is not found by Spring Boot.

By default, Spring Boot searches for schemas on the classpath under graphql/ and its subdirectories. If you place schemas elsewhere, configure schema locations:

~~~yaml
spring:
  graphql:
    schema:
      locations: classpath:graphql/
~~~

If the project configures custom locations, ensure all required schema files reside in those locations. When using multiple locations, check how to declare them for the Spring Boot version in use.

Common causes:

- Files placed in src/main/java instead of src/main/resources.
- Files placed outside the default schema directory without configuring locations.
- Filenames lacking a configured supported extension.
- Files placed in subdirectories not covered by the location pattern.
- Resources not packaged into the artifact during the build.
- Path name or case differences between the development machine and deployment environment.
- A file containing extend type is loaded while the file defining the base type is omitted.

When running in the IDE, resources may be available from the source tree yet missing from the JAR. If the application only fails after packaging, inspect the artifact contents and confirm SDL files are included on the classpath.

## 9. Distinguishing schema errors from RuntimeWiring errors

Schema SDL describes types, fields, arguments, and directives. Runtime wiring connects the schema to execution behavior, such as data fetchers, custom scalars, and type resolvers.

Example schema declaring a custom scalar:

~~~graphql
scalar DateTime

type Event {
    id: ID!
    startsAt: DateTime!
}
~~~

If the application uses the custom scalar DateTime, a matching implementation must be registered in the GraphQL runtime. In Spring for GraphQL, you can provide a RuntimeWiringConfigurer:

~~~java
@Configuration
public class GraphQlConfig {

    @Bean
    RuntimeWiringConfigurer runtimeWiringConfigurer() {
        return wiringBuilder -> {
            // Register GraphQLScalarType DateTime here.
        };
    }
}
~~~

This is a skeleton example; actual registration requires a GraphQLScalarType with coercing suited to the Java type and the API's wire format.

Distinguish between:

- SDL cannot be parsed: syntax error.
- SDL parses, but schema definition is invalid: schema validation/generation error.
- SDL is valid, but a custom scalar or type resolver is not configured: wiring error or execution error, depending on the component and when it is checked.
- Field exists in schema without a custom resolver: GraphQL can use the default property data fetcher on the source object. Therefore, missing a @SchemaMapping method does not necessarily cause schema parsing to fail; the field may return null if no matching property is found.

Do not edit SDL syntax to fix custom scalar or data fetcher issues. Identify the missing runtime component and add the corresponding wiring.

## 10. Client operation errors are not schema parse errors

After the schema loads successfully, clients can still send invalid operations. These are parse or validation errors on the GraphQL document, not schema loading errors at application startup.

Example schema:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
~~~

Client sends a nonexistent field:

~~~graphql
query {
    book(id: "book-42") {
        id
        unknownField
    }
}
~~~

The schema is still valid; the client's operation is rejected because unknownField does not belong to Book.

Common request errors:

- Malformed operation document syntax.
- Field does not exist on the corresponding type.
- Missing non-null argument.
- Variable declared with the wrong type or not supplied.
- Object field missing a selection set.
- Scalar field given a selection set.
- Operation name mismatch when a document contains multiple operations.

These errors usually appear after the endpoint is ready. Read the GraphQL response and request logs to diagnose; do not change the schema if the current schema already matches the contract.

## 11. Reading logs to locate the error

When the application fails to start due to the schema, logs usually contain a root exception wrapped in one or more Spring exceptions. Do not read only the final line like “Application run failed”. Look for the deepest Caused by section and the details provided by the parser/schema generator.

Useful information:

| Information | How to use it |
| --- | --- |
| Filename or resource | Identify which SDL caused the error or could not be found. |
| Line and column | Open the exact spot in the file to inspect the invalid token. |
| Type/field name | Cross-check definitions and references. |
| Expected token message | Check braces, colons, or syntax near the reported location. |
| Scalar/interface/union name | Check implementations, type definitions, or wiring. |
| Startup stack trace | Determine whether the error occurred while creating GraphQlSource or another configuration bean. |

If the log points just past the mistake, inspect a few lines before and after. A missing brace can cause the parser to report an error on the next type declaration.

Do not suppress logging or catch exceptions and continue starting up with a broken schema. The application should fail fast to avoid publishing a GraphQL API that violates its contract.

## 12. Workflow for diagnosing schema parse errors

You can follow this order to narrow down the issue:

1. **Confirm resources are found.** Check that files are on the classpath, extensions are supported, and schema locations are correct.
2. **Identify the file and error position.** Read the root exception, resource name, line, and column.
3. **Check SDL syntax.** Verify type blocks, colons, arguments, lists, non-null markers, enums, and directives.
4. **Check type references.** Confirm every referenced type exists and is used in the proper input/output position.
5. **Check schema composition.** Look for duplicate definitions, extensions missing base types, and duplicate field/argument names.
6. **Check root operations and type relationships.** Verify the Query root, interface implementations, union members, and input object cycles.
7. **Check runtime wiring.** Inspect custom scalars, type resolvers, and GraphQL configuration components.
8. **Send a minimal operation.** Once the application starts, test a simple query before expanding to nested fields and arguments.

Quick decision flow:

~~~mermaid
flowchart TD
    A["Application failed to start?"] -->|Yes| B["Find root error in Caused by"]
    A -->|No| C["Endpoint is ready"]
    B --> D{"SDL found?"}
    D -->|No| E["Fix classpath / schema locations"]
    D -->|Yes| F{"Parser reports syntax?"}
    F -->|Yes| G["Fix SDL at line/column"]
    F -->|No| H{"Schema validation failed?"}
    H -->|Yes| I["Fix type, root, extension, interface, or input"]
    H -->|No| J["Check runtime wiring and configuration beans"]
    C --> K{"Client operation fails?"}
    K -->|Yes| L["Check document, variables, and selection set"]
    K -->|No| M["If resolver fails, check service and data access"]
~~~

When fixing, change only the identified cause, then restart and inspect the new logs. If there are multiple errors, address the first one first; an early parse error can mask subsequent schema errors.

## 13. Combined example: from broken SDL to valid schema

Suppose an application has book.graphqls:

~~~graphql
type Book {
    id ID!
    title: String!
}

type Query {
    book(id: ID!): Book
    books(filter: BookFilter): [Book!]!
}

type BookFilter {
    keyword: String
}
~~~

There are three issues:

1. Field id is missing a colon, so SDL cannot be parsed.
2. BookFilter is declared with type but used as an argument; it is an output object, not an input type.
3. If another file also declares type Query, schema composition may report duplicate definitions.

A fix:

~~~graphql
input BookFilter {
    keyword: String
}

type Book {
    id: ID!
    title: String!
}

type Query {
    book(id: ID!): Book
    books(filter: BookFilter): [Book!]!
}
~~~

If you need to split Query across multiple files, keep the base definition in one file and use extensions in other files:

~~~graphql
extend type Query {
    recentBooks(limit: Int = 10): [Book!]!
}
~~~

After fixing, restart the application and confirm the GraphQL runtime is created successfully. Next, send a simple query:

~~~graphql
query {
    book(id: "book-42") {
        id
        title
    }
}
~~~

If this operation succeeds, you can proceed to test filters, nested mappings, and more complex resolvers.

## 14. Common errors and resolutions

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Schema resource not found | Wrong classpath, location, or extension. | Check src/main/resources/graphql/, schema locations, and JAR contents. |
| Parser reports error near brace | Missing or extra {, }, (, ), or :. | Inspect lines preceding the parser-reported location as well. |
| Unknown type | Typo in type name or defining file not loaded. | Check spelling and schema locations. |
| Type used in wrong position | type used instead of input or vice versa. | Distinguish input types and output types. |
| Duplicate type/field | Multiple files duplicate definitions instead of extending. | Use extend type and manage base types clearly. |
| Invalid Query root | Missing root Query or schema definition points to wrong type. | Declare Query object or corresponding root operation. |
| Interface validation failure | Object lacks field or has incompatible type. | Match all fields required by the interface. |
| Custom scalar does not work | Missing or wrong scalar wiring/coercing. | Register GraphQLScalarType via runtime wiring. |
| Application starts but field returns null | No matching resolver or source object lacks corresponding property. | Check property access and @SchemaMapping. |
| Client reports field does not exist | Operation does not match current schema. | Fix operation or intentionally update schema. |

## 15. Key takeaways

- Spring Boot loads SDL from the classpath via schema locations; file locations and extensions must match the configuration.
- Parse errors are syntax errors; schema validation/generation errors are errors in relationships and rules between types.
- Runtime wiring, request validation, and resolver execution are separate stages.
- Use extend type to extend previously declared types when a schema is split across multiple files.
- Verify the Query root, input/output type positions, duplicate definitions, interface implementations, and union members.
- Read the root exception, resource name, line, and column before making fixes.
- After the schema builds successfully, test a simple operation first before testing complex resolvers.
- Do not confuse a missing @SchemaMapping with an SDL parse error; a field may use the default property data fetcher.

Once you understand each stage of loading and building a schema, handling schema parse errors in Spring for GraphQL becomes systematic. Start from the resources and root exception, identify the error layer, fix the SDL or runtime wiring appropriately, and verify again with a minimal operation.
