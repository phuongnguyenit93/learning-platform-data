# Organizing multiple schema files in Spring for GraphQL

A GraphQL schema can be split across multiple SDL files to group types and fields by feature. Spring for GraphQL together with Spring Boot supports reading multiple schema resources and combining them into a single `GraphQLSchema` before serving requests.

Splitting files keeps large schemas readable, easy to navigate, and easy to assign domain ownership. However, GraphQL still validates the entire schema as one unified contract: type names must be unique, extensions must be valid, and all type references must resolve in the final schema.

## 1. Why split a schema across multiple files?

Early on, an application may only need a single `schema.graphqls` file. As the API grows, that file accumulates many root fields, object types, input types, enums, and directives. An oversized file makes it hard to locate definitions, review changes, and see which parts belong to which domain.

For example, a library management application might organize its schema by area:

- `common`: shared scalars, enums, and directives.
- `book`: types, inputs, and operations related to books.
- `author`: types, inputs, and operations related to authors.
- `member`: types and operations related to members.
- `schema`: root types or API-wide definitions.

These files do not create separate GraphQL endpoints or independent schemas. They are merged into one schema, so clients still send operations to a single GraphQL endpoint and can select fields from multiple domains in one query.

## 2. How GraphQL combines SDL definitions

GraphQL SDL supports two ways to organize definitions:

1. **Type definition** declares a new type, such as `type Book`, `input BookInput`, or `enum BookStatus`.
2. **Type extension** extends an already declared type, such as `extend type Query` adding root fields from another domain.

When a schema is split across multiple files, each type should normally have only one base definition. Domain files add fields to root types or shared types using `extend`.

### 2.1. Declaring root types once

The file `graphql/schema.graphqls` can hold foundational API fields:

~~~graphql
type Query {
    apiVersion: String!
}
~~~

This is the base definition of `Query`. Other files can add fields using `extend type Query`.

If the API uses the default root type names `Query`, `Mutation`, and `Subscription`, GraphQL does not require a `schema { ... }` block. If you need custom root type names, declare the schema definition once in the base file:

~~~graphql
schema {
    query: RootQuery
    mutation: RootMutation
}

type RootQuery {
    apiVersion: String!
}

type RootMutation {
    noop: Boolean!
}
~~~

Do not repeat multiple `schema { ... }` blocks across domain files. Domains only extend the designated root type, such as `extend type RootQuery`.

### 2.2. Using type extensions to add fields

Suppose the book domain has a `Book` type and two queries. The file `graphql/book/book.graphqls` declares:

~~~graphql
type Book {
    id: ID!
    title: String!
    author: Author
}

extend type Query {
    book(id: ID!): Book
    books: [Book!]!
}
~~~

The author domain can declare its own type and add queries to the same root type in `graphql/author/author.graphqls`:

~~~graphql
type Author {
    id: ID!
    name: String!
    books: [Book!]!
}

extend type Query {
    author(id: ID!): Author
    authors: [Author!]!
}
~~~

`Book` references `Author`, and `Author` references back to `Book`. This is valid because GraphQL validates definitions across the combined schema; a type is not required to be declared in the same file as the types referencing it.

After merging the files, the root `Query` type has fields `apiVersion`, `book`, `books`, `author`, and `authors`. Clients can query data from both domains in a single operation:

~~~graphql
query LibraryOverview {
    books {
        id
        title
        author {
            id
            name
        }
    }
    authors {
        id
        name
    }
}
~~~

Corresponding resolvers are still implemented via Spring for GraphQL controllers and services. Splitting SDL files does not change how `@QueryMapping`, `@MutationMapping`, or `@SchemaMapping` are mapped.

## 3. Suggested schema directory structure

Spring Boot searches for schemas by default under `classpath:graphql/**/` with `.graphqls` and `.gqls` extensions. You can use subdirectories to group files by domain:

~~~text
src/main/resources/
└── graphql/
    ├── schema.graphqls
    ├── common/
    │   ├── scalars.graphqls
    │   ├── enums.graphqls
    │   └── directives.graphqls
    ├── book/
    │   ├── book.graphqls
    │   ├── book-input.graphqls
    │   └── book-mutation.graphqls
    ├── author/
    │   ├── author.graphqls
    │   └── author-query.graphqls
    └── member/
        ├── member.graphqls
        └── member-mutation.graphqls
~~~

This is a reference layout, not a mandatory structure. For small schemas, a few domain files are sufficient. Avoid creating too many tiny files just to isolate individual types; the goal is to help developers find related parts of the API contract in one area.

### 3.1. Splitting files by domain instead of only by type kind

There are two common approaches:

| Splitting approach | Example | Characteristics |
| --- | --- | --- |
| By declaration kind | `queries.graphqls`, `mutations.graphqls`, `types.graphqls` | Easy to browse by GraphQL construct while small, but a single domain gets scattered across many files |
| By domain | `book.graphqls`, `author.graphqls`, `member.graphqls` | Keeps related types, inputs, and fields together; works well as the API grows by business domain |

For applications with multiple domains, splitting by domain is usually more convenient. You can keep a few shared files for scalars, directives, and enums genuinely used across domains.

## 4. Sharing root fields across domains

`Query`, `Mutation`, and `Subscription` are root types shared by multiple domains. Declare each base type once, then extend it in domain files.

Example file `graphql/schema.graphqls`:

~~~graphql
type Query {
    apiVersion: String!
}

type Mutation {
    healthCheck: Boolean!
}
~~~

File `graphql/book/book-mutation.graphqls`:

~~~graphql
input CreateBookInput {
    title: String!
    authorId: ID!
}

extend type Mutation {
    createBook(input: CreateBookInput!): Book!
    deleteBook(id: ID!): Boolean!
}
~~~

File `graphql/member/member-mutation.graphqls`:

~~~graphql
input RegisterMemberInput {
    email: String!
    displayName: String!
}

extend type Mutation {
    registerMember(input: RegisterMemberInput!): Member!
}
~~~

Domain files can extend the same `Mutation` type without editing the root file whenever new functionality is added. Ensure every field name within a given object type is unique. If two domains both declare `create` without clear naming conventions, the schema will conflict or the API will become confusing.

Similarly, you can use `extend type Subscription` to organize event streams by domain:

~~~graphql
extend type Subscription {
    bookCreated: Book!
}
~~~

This extension assumes `type Subscription` has already been declared as a base type in the foundational schema. Subscription fields still require resolvers returning publishers and a transport supporting subscriptions. Type extensions only merge the schema; they do not create event sources automatically.

## 5. Sharing scalars, enums, inputs, and directives

Shared definitions should live in the `common` area and be declared exactly once.

### 5.1. Custom scalars

File `graphql/common/scalars.graphqls`:

~~~graphql
scalar DateTime
scalar BigDecimal
~~~

Declaring `scalar DateTime` in SDL only creates the type name. The application must still register the corresponding implementation in runtime wiring, for example via `RuntimeWiringConfigurer` or `GraphQlSourceBuilderCustomizer`:

~~~java
@Bean
RuntimeWiringConfigurer scalarConfigurer() {
    return wiring -> wiring
            .scalar(ExtendedScalars.DateTime)
            .scalar(ExtendedScalars.GraphQLBigDecimal);
}
~~~

The example above illustrates registering scalars provided by the Extended Scalars library; scalar names in SDL and implementations must match. If you define a custom `Money` scalar yourself, declare `scalar Money` in SDL and provide a matching `GraphQLScalarType` with parsing, serialization, and validation rules.

### 5.2. Enums and input types

File `graphql/common/enums.graphqls`:

~~~graphql
enum SortDirection {
    ASC
    DESC
}

enum BookStatus {
    DRAFT
    PUBLISHED
    ARCHIVED
}
~~~

The book domain can reference `BookStatus` in types or inputs:

~~~graphql
input BookFilterInput {
    status: BookStatus
    keyword: String
}
~~~

Shared enum definitions give domains a consistent representation of states. However, share an enum only when its business semantics are truly identical; two values with similar names but different rules should be defined separately.

### 5.3. Directives

File `graphql/common/directives.graphqls` can declare custom directives:

~~~graphql
directive @upperCase on FIELD_DEFINITION
~~~

A domain uses the directive:

~~~graphql
type MemberProfile {
    id: ID!
    displayName: String! @upperCase
}
~~~

A directive declaration only describes where the directive is valid. For a directive to alter execution behavior, the application must implement directive wiring or an equivalent mechanism in GraphQL Java. Moving the declaration to a separate file does not register runtime behavior automatically.

## 6. Configuring Spring Boot to load multiple files

With `spring-boot-starter-graphql`, you do not need to load files manually if resources reside in the default location. The starter automatically discovers schema resources according to `spring.graphql.schema.locations` and supported extensions.

The default configuration effectively corresponds to:

~~~yaml
spring:
  graphql:
    schema:
      locations: classpath:graphql/**/
~~~

The pattern `classpath:graphql/**/` searches inside `graphql` and its subdirectories. Thus files in `graphql/book`, `graphql/author`, and `graphql/common` are all discovered.

If schemas reside elsewhere, you can customize locations:

~~~yaml
spring:
  graphql:
    schema:
      locations:
        - classpath:graphql/**/
        - classpath:shared-graphql/**/
~~~

When changing locations, verify that all desired resources are included. Setting a custom location can cause the application to miss files still sitting in the default directory unless both are listed.

### 6.1. File extensions

Spring Boot supports `.graphqls` and `.gqls` schema extensions by default. Use one extension consistently within a project so developers can easily identify SDL files. If you modify `spring.graphql.schema.file-extensions`, confirm the new setting covers all file types in use.

### 6.2. Packaging schemas in a JAR

Schemas placed under `src/main/resources` are packaged onto the application's classpath. When running from an IDE, files may be read from the resources folder; when running a JAR, resources are read from inside the JAR. Avoid OS filesystem paths like `C:/project/schema.graphqls`, as those paths break when deployed to other environments.

## 7. Loading schema resources manually

If you are not using Spring Boot auto-configuration or want to construct `GraphQlSource` manually, Spring for GraphQL provides `GraphQlSource.schemaResourceBuilder()` to specify multiple resources:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;
import org.springframework.graphql.execution.GraphQlSource;

@Configuration(proxyBeanMethods = false)
public class ManualGraphQlSourceConfiguration {

    @Bean
    GraphQlSource graphQlSource(RuntimeWiringConfigurer runtimeWiringConfigurer) {
        return GraphQlSource.schemaResourceBuilder()
                .schemaResources(
                        new ClassPathResource("graphql/schema.graphqls"),
                        new ClassPathResource("graphql/common/scalars.graphqls"),
                        new ClassPathResource("graphql/book/book.graphqls"),
                        new ClassPathResource("graphql/author/author.graphqls")
                )
                .configureRuntimeWiring(runtimeWiringConfigurer::configure)
                .build();
    }
}
~~~

This is a manual configuration example: the application must supply all required resources and runtime wiring. When defining your own `GraphQlSource` bean in a Spring Boot app, the default auto-configured source backs off due to missing-bean conditions. Any configuration previously supplied by auto-configuration must then be transferred to the manual configuration.

For Boot starter applications, prefer `spring.graphql.schema.locations` if you only need extra directories. Use the manual builder when you need direct control over source creation or when not using auto-configuration.

## 8. Java resolvers do not depend on the number of SDL files

After the files are merged, the GraphQL engine sees a single unified schema. Spring for GraphQL still maps resolvers by type and field name.

Example controller for book domain queries:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id).orElse(null);
    }

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }
}
~~~

The controller for the author domain can live in a separate class:

~~~java
@Controller
public class AuthorController {

    private final AuthorService authorService;

    public AuthorController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @QueryMapping
    public Author author(@Argument String id) {
        return authorService.findById(id).orElse(null);
    }

    @QueryMapping
    public List<Author> authors() {
        return authorService.findAll();
    }
}
~~~

By default, the method name is used as the field name unless another name is specified in the annotation. If multiple controllers map the same field or two resolvers share the same type and field mapping, resolve the conflict explicitly. Splitting SDL across files does not automatically isolate resolvers or namespace fields.

When an object type has a field linking to another domain, `@SchemaMapping` or `@BatchMapping` still works across the combined schema. For example, `Book.author` can be resolved by a method in `BookController`, even though `Author` is defined in another SDL file.

## 9. Key rules when splitting a schema

### 9.1. Do not declare duplicate types

Do not define `type Query` across multiple files as if each file were an independent schema. This creates definition conflicts. Declare one base type and extend it in domain files:

~~~graphql
# schema.graphqls
type Query {
    apiVersion: String!
}

# book.graphqls
extend type Query {
    books: [Book!]!
}
~~~

The same rule applies to object types, input types, enums, interfaces, and unions: use type extensions when adding members to an existing definition and ensure extensions are valid for the GraphQL Java version in use.

### 9.2. Type extensions require a base type

`extend type Query` does not create `Query` from scratch. If no file declares `type Query`, schema validation will fail. Keep base root type definitions in a foundational file or ensure a base definition exists elsewhere.

### 9.3. Declare scalars, directives, and schema definitions once

Declarations such as `scalar DateTime`, `directive @upperCase ...`, and `schema { ... }` should have one clear owner. Domain files simply reference the declared names. Duplicate definitions can cause parser errors or make the schema hard to maintain.

### 9.4. Do not rely on filename ordering

Do not use prefixes like `01-`, `02-`, `03-` assuming one file is parsed before another. Design the schema with valid definitions and extensions across the whole resource set. Referencing a type declared in another file is normal; the schema must be valid once all resources are loaded.

### 9.5. Watch for field name and enum value collisions

Each object type can have only one field with a given name. Likewise, enums cannot contain duplicate values. When multiple domains contribute fields to the same root type, choose specific names—such as `book`, `createBook`, `registerMember`—instead of generic ones like `get`, `create`, or `search`.

### 9.6. Keep nullability consistent

When a domain extends a type defined in another file, align on nullability conventions and field semantics. For example, `[Book!]!` guarantees the list always exists and elements are non-null; `Book` permits a null result. These guarantees directly impact responses and GraphQL null propagation.

## 10. Testing multi-file schemas

The most important check is verifying `GraphQlSource` initializes cleanly from all resources and executes operations spanning fields from multiple files.

In Spring Boot applications, you can use the `@GraphQlTest` slice test and `GraphQlTester`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;

@GraphQlTest
class MultiFileSchemaTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void combinesBookAndAuthorFields() {
        graphQlTester.document("""
                query {
                    books {
                        id
                        title
                        author {
                            id
                            name
                        }
                    }
                }
                """)
            .execute()
            .path("books[0].author.name")
            .entity(String.class)
            .isEqualTo("Author One");
    }
}
~~~

This test assumes the slice test includes controller/service fixtures and test data containing a book whose author is named `Author One`. The query selects `Book` and `Author` together, confirming that types referenced across files coexist in the final schema and resolvers return data.

Additional recommended checks:

1. The application context starts cleanly when loading all schema resources.
2. Root types are declared once and domain files extend the right root types.
3. Query, mutation, and subscription fields across files map to their corresponding resolvers.
4. Custom scalars and directives used in domain files are registered in runtime wiring.
5. Missing SDL files, extensions without base types, or duplicate declarations fail schema initialization.
6. The packaged JAR contains all schema resources, rather than working only inside the IDE.

If you need to inspect the schema without starting a web server, inject `GraphQlSource` and inspect `schema()`, or use `ExecutionGraphQlService` with an appropriate `GraphQlTester`. For HTTP endpoint tests, use `HttpGraphQlTester` to verify routing and transport as well.

## 11. Common errors when organizing multiple files

| Error | Cause | How to fix |
| --- | --- | --- |
| `Type ... not found` | Resource defining the type was not loaded, or type name is misspelled | Check schema locations, file extensions, and type names |
| `Type ... already defined` | Multiple files declare the same base type | Switch additional contributions to `extend type` |
| `Cannot extend type ... because it is not defined` | Extension exists without a base definition | Create the base type in the foundational file and verify resource paths |
| Field exists in SDL but client cannot call it | Field is missing from final schema or request hits an older build | Check resource discovery, build artifacts, and restart the application |
| Scalar has no implementation | Scalar was only declared in SDL | Register `GraphQLScalarType` in runtime wiring |
| Works in IDE but fails from JAR | Schema resource was not packaged or path uses OS filesystem | Place files under `src/main/resources` and use classpath resources |
| Two domains add identically named fields | Root type has duplicate field names | Name fields by domain and validate the merged schema |

When encountering errors, read the schema parsing or validation message at startup. It typically points directly to the conflicting file, line, or type name.

## 12. Workflow for organizing schema for a new domain

When adding a new domain to a GraphQL API, you can follow these steps:

1. Identify the object types, input types, enums, and scalars the domain needs.
2. Place the domain definitions in a dedicated subdirectory under `src/main/resources/graphql`.
3. Declare root types in the foundational file; use `extend type Query`, `extend type Mutation`, or `extend type Subscription` in domain files.
4. Reuse shared types from `common`; do not redeclare existing scalars, directives, or enums.
5. Write Java resolvers using appropriate mapping annotations and keep business logic in services.
6. Verify the merged schema, runtime wiring, nullability, and field names.
7. Run `GraphQlTester` or integration tests to confirm cross-domain operations work properly.

Splitting a schema by domain keeps the GraphQL contract organized as it grows. What matters most is that all files still merge into a single valid schema consistent with resolvers, runtime wiring, and business rules in Spring for GraphQL.

## References

- [Spring Boot — Spring for GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Spring Boot — GraphQL Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html#appendix.application-properties.web.spring.graphql.schema)
- [Spring for GraphQL — Request Execution and GraphQlSource](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — GraphQlSource API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/GraphQlSource.html)
- [GraphQL Specification — Type System Extensions](https://spec.graphql.org/October2021/#sec-Type-System-Extensions)
