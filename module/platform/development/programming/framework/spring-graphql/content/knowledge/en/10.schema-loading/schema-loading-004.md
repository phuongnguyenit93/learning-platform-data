# Multiple schema resources

A GraphQL schema can contain many object types, input types, enums, scalars, interfaces, unions, and root operations. As a schema grows, placing all SDL in a single file makes searching, reviewing, and coordinating changes difficult. Spring for GraphQL lets you organize a schema into multiple SDL resources, which Spring Boot discovers and combines into a single executable schema.

It is important to understand that splitting files is only a way of organizing resources. The GraphQL server still uses a unified schema when validating and executing operations. Types and fields must be valid when evaluated across the entire set of loaded resources. In Spring Boot, resource locations and file extensions are configured via the **spring.graphql.schema.*** properties.

This lesson covers splitting SDL by domain, defining and extending types across files, how Spring Boot discovers multiple schema resources, checking the classpath and packaging, and common errors when merging schemas.

## 1. Why split a schema into multiple resources?

A small schema can start in a single file:

~~~graphql
type Query {
  book(id: ID!): Book
  authors: [Author!]!
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
~~~

As the API grows, the schema may gain dozens or hundreds of types and fields. A single file easily runs into problems:

- Difficult to locate a domain type's definition.
- Multiple people edit the same file and easily cause merge conflicts.
- Hard to review changes because unrelated business concerns sit next to each other.
- Long schema files make reading and maintenance inconvenient.
- Hard to separate shared definitions from domain-specific ones.

You can split the schema by business group:

~~~text
src/main/resources/
└── graphql/
    ├── common.graphqls
    ├── book/
    │   ├── book.graphqls
    │   ├── book-query.graphqls
    │   └── book-relations.graphqls
    ├── author/
    │   ├── author.graphqls
    │   └── author-query.graphqls
    └── order/
        ├── order.graphqls
        └── order-mutation.graphqls
~~~

Each file can focus on a group of types or an extension. Spring Boot loads the resources matching the location pattern and combines their definitions.

Splitting files helps organize source code, but does not create multiple GraphQL endpoints or multiple independent schemas. If clients call the same GraphQL server, operations are still validated against the merged schema.

## 2. Where does Spring Boot search for schema resources?

With Spring Boot and Spring for GraphQL, SDL files are typically placed in the resource directory:

~~~text
src/main/resources/graphql/
~~~

The default location is commonly represented by the resource pattern:

~~~properties
spring.graphql.schema.locations=classpath:graphql/**/
~~~

Spring Boot searches for schema files in the configured location. The extensions commonly supported by default are:

~~~properties
spring.graphql.schema.file-extensions=.graphqls,.gqls
~~~

You can explicitly set these properties in **application.properties**:

~~~properties
spring.graphql.schema.locations=classpath:graphql/**/
spring.graphql.schema.file-extensions=.graphqls,.gqls
~~~

Or use YAML:

~~~yaml
spring:
  graphql:
    schema:
      locations: classpath:graphql/**/
      file-extensions:
        - .graphqls
        - .gqls
~~~

These values clarify the resource pattern and file types searched. If you rely on the defaults of the Spring Boot version you are running, you do not necessarily need to redeclare them.

### Meaning of classpath resources

The **classpath:** prefix indicates that resources are searched on the application's classpath. When running in an IDE, resources are typically copied to the output directory. When packaged as a JAR, resources reside inside the artifact and are read from the classpath at runtime.

Therefore, do not place schemas at a personal machine path and expect the production application to find the file automatically. A path relative to the working directory may work on a developer machine but fail inside a container or when launched from another directory.

If schemas are distributed across multiple modules or dependency JARs, check whether the resource pattern can locate resources across all intended classpath locations. A pattern like **classpath*:** may be needed depending on packaging and the application's resource resolution mechanism. Verify on the actual artifact instead of only testing from the IDE.

## 3. How Spring combines multiple SDL files

Spring Boot locates schema resources based on configuration and passes them to the GraphQL schema building process. GraphQL Java parses the loaded SDL definitions and builds a merged schema.

Example **book.graphqls** file:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

**author.graphqls** file:

~~~graphql
type Author {
  id: ID!
  name: String!
}

extend type Query {
  authors: [Author!]!
}
~~~

After the resources are loaded, the merged schema has a root Query with both **book** and **authors** fields, along with the two object types **Book** and **Author**.

Combining does not mean concatenating file contents as arbitrary text while ignoring GraphQL rules. The final set of definitions must still be valid:

- Every referenced type must exist.
- Each type must have a valid definition.
- Fields must not be redundantly defined in conflicting ways.
- Extensions must match their base types.
- Root operation types must be properly defined.
- Interfaces, unions, inputs, and enums must adhere to type system rules.

If a file is invalid, the schema may fail to build and the application usually fails during startup. This is helpful behavior because schema errors are caught early instead of waiting until a client calls the problematic field.

## 4. Using type and extend type across files

When splitting SDL, one file typically defines the base type; other files can extend that type using **extend type**.

For example, **book.graphqls** defines:

~~~graphql
type Book {
  id: ID!
  title: String!
}

type Query {
  book(id: ID!): Book
}
~~~

**book-relations.graphqls** adds relationships:

~~~graphql
type Author {
  id: ID!
  name: String!
}

extend type Book {
  author: Author!
}
~~~

**book-search.graphqls** extends the root Query:

~~~graphql
extend type Query {
  booksByTitle(prefix: String!): [Book!]!
}
~~~

The merged schema has the fields:

- **Query.book**
- **Query.booksByTitle**
- **Book.id**
- **Book.title**
- **Book.author**
- **Author.id**
- **Author.name**

**extend type** helps separate responsibilities across files. However, the extended type must have a definition in the merged schema. You cannot extend a nonexistent type just because the extension file is loaded from the same directory.

### Define the base type only once

There should be one place defining the base type and extensions in the remaining files. For example:

~~~graphql
type Query {
  book(id: ID!): Book
}
~~~

In another file:

~~~graphql
extend type Query {
  authors: [Author!]!
}
~~~

Do not repeat **type Query** across multiple files for the purpose of adding fields. GraphQL SDL has extension syntax for that. Using multiple base type definitions with the same name can cause schema errors when the parser merges them.

Mutation and Subscription can also be extended in the same way:

~~~graphql
type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

Another file:

~~~graphql
extend type Mutation {
  archiveBook(id: ID!): Book!
}
~~~

Root Mutation and Subscription are optional. If the schema uses them, define the base root type before other files extend it.

## 5. Organizing a schema by domain

For a catalog application, you can organize files by domain and declaration kind:

~~~text
graphql/
├── common/
│   ├── scalars.graphqls
│   └── pagination.graphqls
├── book/
│   ├── book-types.graphqls
│   ├── book-inputs.graphqls
│   ├── book-queries.graphqls
│   ├── book-mutations.graphqls
│   └── book-relations.graphqls
├── author/
│   ├── author-types.graphqls
│   ├── author-queries.graphqls
│   └── author-relations.graphqls
└── order/
    ├── order-types.graphqls
    ├── order-inputs.graphqls
    └── order-mutations.graphqls
~~~

Example **common/scalars.graphqls**:

~~~graphql
scalar DateTime
scalar Money
~~~

Example **book/book-types.graphqls**:

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

Example **book/book-queries.graphqls**:

~~~graphql
type Query {
  book(id: ID!): Book
}
~~~

Example **author/author-queries.graphqls**:

~~~graphql
type Author {
  id: ID!
  name: String!
}

extend type Query {
  author(id: ID!): Author
}
~~~

Example **book/book-relations.graphqls**:

~~~graphql
extend type Book {
  author: Author
}
~~~

This split helps developers find definitions by domain. A team that prefers feature-based files can put related types, inputs, and fields in the same directory; another team may prefer separating types/inputs/queries/mutations into individual files. Both are valid as long as the structure is clear and creates no duplicates.

### Avoid mechanically splitting files too finely

Every file should have a reason to exist. One file per field can make navigation harder and scatter extensions everywhere. Conversely, one giant file for every domain reduces the benefits of splitting.

Choose boundaries based on:

- Domain or bounded context.
- Related groups of types and relationships.
- Team ownership.
- Change frequency and review style.
- Reusability across parts of the schema.

## 6. Multiple resources are not an SDL import mechanism

Standard GraphQL SDL has no universal **import** or **include** statement for one file to load another. In Spring Boot, discovering multiple files is the responsibility of resource loading configuration and the schema builder.

For example, do not assume the following syntax is understood by GraphQL Java:

~~~graphql
import "book.graphqls"
~~~

This is not standard GraphQL SDL import syntax. Instead, place files in the configured resource location so Spring Boot loads them all, or customize the schema resource builder when special requirements exist.

Similarly, **extend type** is not a file import. It is GraphQL syntax for extending an existing type in the merged schema.

Distinguish the three concepts:

| Concept | Responsibility |
|---|---|
| Resource location/pattern | Specifies where Spring looks for SDL files |
| Loading multiple schema resources | Collects files and passes them to the schema builder |
| **extend type** | Extends a GraphQL type definition within the schema |

Understanding these three layers prevents searching for an import syntax that does not exist in standard SDL.

## 7. Configuring schema locations by environment

Normally, the schema is part of the application and packaged with the artifact. If there is a reason to change the resource location, it can be configured via profiles.

**application.properties**:

~~~properties
spring.graphql.schema.locations=classpath:graphql/**/
spring.graphql.schema.file-extensions=.graphqls,.gqls
~~~

**application-test.properties**:

~~~properties
spring.graphql.schema.locations=classpath:graphql-test/
~~~

**application-prod.properties**:

~~~properties
spring.graphql.schema.locations=classpath:graphql/
~~~

Activate a profile via an environment variable:

~~~bash
SPRING_PROFILES_ACTIVE=test
~~~

However, using different schemas between test and production can cause tests not to reflect the deployed contract accurately. For most projects, use the same schema resources and vary data, services, or runtime configuration per environment. Only separate schema locations when there is a specific requirement and checks are in place to ensure the two schemas do not drift unintentionally.

If the schema is supplied from a directory outside the artifact, determine packaging, volume mounts, and process file read permissions. Avoid using a developer's local path as production configuration.

## 8. Extending the schema with Java when needed

In cases where simple resource configuration does not meet requirements, Spring Boot allows customizing `GraphQlSource` creation via extension points such as **GraphQlSourceBuilderCustomizer** or configuring `GraphQlSource` appropriate to the version in use.

Situations that may require customization:

- Schema resources are provided dynamically from a controlled source.
- Need to register custom scalars or a TypeResolver.
- Need to add runtime wiring for data fetchers, directives, or instrumentation.
- Need to control schema construction outside default auto-configuration.

For most applications, start with **spring.graphql.schema.locations** and static SDL resources. Only use Java customization when there is a specific need, because creating your own `GraphQlSource` or replacing the default bean can cause part of auto-configuration to no longer apply.

An example of runtime wiring typically registered via a **RuntimeWiringConfigurer** bean:

~~~java
@Configuration
public class GraphQlRuntimeConfiguration {

    @Bean
    RuntimeWiringConfigurer runtimeWiringConfigurer() {
        return wiringBuilder -> {
            // Register custom scalars, TypeResolver, or data fetchers
            // matching the loaded schema.
        };
    }
}
~~~

This bean adds runtime wiring to the schema. It does not replace discovering and loading SDL resources. Keep the two responsibilities distinct: schema resources describe types and fields; runtime wiring provides how fields execute or how values are converted.

## 9. Verifying packaged resources

A common error is a schema working in the IDE but not being found when running the JAR. The cause usually lies in the resource path, file extension, or artifact build process.

Check:

1. SDL files are inside **src/main/resources** or a properly configured resource source set.
2. Files have extensions listed in **spring.graphql.schema.file-extensions**.
3. The resource pattern covers the right subdirectories.
4. The active profile does not override the location to a nonexistent path.
5. SDL files are actually packaged inside the JAR.
6. If resources come from another dependency, verify whether the classpath pattern locates them.

You can use the JDK command to list JAR contents:

~~~bash
jar tf build/libs/book-catalog.jar
~~~

Look for paths like:

~~~text
BOOT-INF/classes/graphql/book/book-types.graphqls
BOOT-INF/classes/graphql/author/author-types.graphqls
~~~

If the files do not appear in the JAR, the issue lies in resource packaging before Spring GraphQL begins loading the schema.

## 10. Testing the merged schema

A schema split across multiple files still needs to be tested as a single contract. You can test at multiple levels:

### Checking at application startup

Spring Boot creates `GraphQlSource` when the application context initializes. Invalid SDL syntax, missing types, or invalid extensions can prevent the application from starting.

This is why you should let the application validate the schema right inside the test context. Do not delay discovering errors until production deployment.

### Testing operations with GraphQlTester

Once the schema is loaded, you can use `GraphQlTester` to verify that fields defined across different resources work together:

~~~java
@SpringBootTest
class BookSchemaIntegrationTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void shouldResolveBookAndAuthorFields() {
        graphQlTester.document("""
                query {
                    book(id: "book-01") {
                        title
                        author {
                            name
                        }
                    }
                }
                """)
            .execute()
            .path("book.title")
            .entity(String.class)
            .isEqualTo("Spring GraphQL");
    }
}
~~~

This test verifies the merged schema, resolver mappings, and test data. It does not just confirm that a single file is read, but confirms that definitions work together in a single operation.

### Checking the entire schema in CI

In your pipeline, initialize the Spring application context or run integration tests with `GraphQlSource` to detect schema errors before packaging and deployment. If your project has schema compatibility rules, you can add breaking-change checks between the current schema and the previous version's schema.

## 11. Common errors when splitting into multiple schema resources

| Symptom | Possible cause | Resolution |
|---|---|---|
| Application cannot find Query | Missing root Query or resource containing Query not loaded | Check root type and location pattern |
| **extend type Query** reports type does not exist | Base definition file is not in the loaded resource set | Check location, extension, and type name |
| Duplicate type definition | Multiple files define the same base type | Keep one base definition, use **extend type** |
| Field declared twice | Multiple extensions add the same field | Find and remove duplicate definition |
| Type does not exist | Typo in type name or resource containing type omitted | Check references and file packaging |
| SDL works in IDE but fails in JAR | Resource not packaged or different path | Check artifact contents and classpath |
| A file is not read | Extension is not in the searched list | Check **.graphqls**/**.gqls** and file-extensions |
| Profile configuration has no effect | Profile not active or property overridden | Check active profile and config sources |
| Expecting **extend type** to find files automatically | Confusing type extension with resource loading | Configure resource locations separately |
| Test schema differs from production | Different locations used across profiles | Test the same schema or manage differences intentionally |

When an error occurs, inspect the startup message from the GraphQL schema parser. The error usually points to the conflicting type, field, or extension name. Fix the actual base definition or resource pattern rather than adding a duplicate type name to work around it.

## 12. Principles for organizing multiple schema resources

Several principles keep schemas maintainable:

- **One base type, controlled extensions:** avoid multiple files defining the same type.
- **Split by domain:** keep related types, inputs, and fields close together.
- **Meaningful filenames:** filenames should tell developers what kind of declarations they contain.
- **Keep root types clear:** define root Query/Mutation/Subscription in an easy-to-find place; use extensions to add fields.
- **Avoid file order dependencies:** the merged schema must be valid regardless of the order resources are discovered.
- **Do not assume imports:** let Spring manage resource discovery; use **extend type** for type extensions.
- **Inspect artifacts:** ensure schema resources are included in the deployed JAR or image.
- **Test the merged schema:** run context tests and representative operations in CI.
- **Review changes as API contracts:** changes to fields, nullability, and root operations can affect clients.

## 13. Workflow for adding a new schema resource

When adding a new domain to the GraphQL API, you can follow these steps:

1. Identify the domain and the objects/inputs/enums/scalars to expose.
2. Locate the root types and existing types that the domain needs to reference.
3. Place **.graphqls** or **.gqls** files in the appropriate resource location.
4. Define new types; use **extend type** when adding fields to existing types.
5. Verify no types or fields are duplicated.
6. Add the corresponding resolvers and runtime wiring in Spring for GraphQL.
7. Initialize the application context to confirm the schema loads and is valid.
8. Write `GraphQlTester` tests for operations traversing the newly added types.
9. Verify the resources appear in the build artifact.
10. Include schema tests in CI so errors are caught before deployment.

Multiple schema resources allow splitting SDL into smaller parts by domain and make team collaboration easier. Spring Boot discovers resources by configured locations and extensions; GraphQL Java combines the definitions into a unified schema. **extend type** extends existing types, while resolvers and runtime wiring in Spring for GraphQL provide execution behavior. When resources are organized clearly, duplicates are avoided, and the merged schema is tested in CI, an application can scale its GraphQL API while maintaining a consistent contract for clients.
