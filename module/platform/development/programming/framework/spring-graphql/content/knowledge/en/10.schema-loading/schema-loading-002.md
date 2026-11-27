# Schema files in the classpath

Spring for GraphQL typically uses a **schema-first** approach: the API is described using GraphQL SDL in resource files, while Java controllers and resolvers provide data for the declared fields. With Spring Boot, you do not need to manually read each SDL file or concatenate them into a single string. Auto-configuration locates schema resources on the classpath, loads them, and builds the runtime schema for GraphQL Java.

The default location is `classpath:graphql/**/`; files with `.graphqls` or `.gqls` extensions are recognized by default. You can split the schema across multiple files and directories by domain, as long as the combined definitions form a valid schema.

This lesson explains classpath resources, default locations and extensions, how to organize multiple SDL files, how to configure custom locations, the impact of application packaging, and how to diagnose issues when Spring cannot find the schema.

## 1. What is a classpath resource?

The classpath is the set of directories and libraries that the JVM uses to locate classes and resources when an application runs. In a Spring Boot project, resources placed in `src/main/resources` are typically copied to the classpath during the build.

Example project structure:

```text
src/
└── main/
    ├── java/
    │   └── com/example/library/
    │       ├── LibraryApplication.java
    │       └── graphql/
    │           └── BookController.java
    └── resources/
        ├── application.yml
        └── graphql/
            ├── book.graphqls
            ├── author.graphqls
            └── review/
                └── review.graphqls
```

After building, resources typically reside in the build tool's output directory, such as `build/resources/main` for Gradle or `target/classes` for Maven. When packaging a Spring Boot executable JAR, application resources are placed into the JAR's classpath section, usually under `BOOT-INF/classes/`.

This means an application running from an IDE, from a build directory, or from an executable JAR can still locate schemas using the same classpath location. Avoid relying on relative paths from the development machine such as `C:/project/src/main/resources/graphql` because that path does not exist in deployment environments.

## 2. Default Spring Boot schema location

When using `spring-boot-starter-graphql`, Spring Boot auto-configures `GraphQlSource` to locate SDL resources. The default location is:

```text
classpath:graphql/**/
```

This pattern searches for resources in the `graphql` directory on the classpath, including subdirectories. Therefore, both of the following locations are found:

```text
src/main/resources/graphql/book.graphqls
src/main/resources/graphql/review/review.graphqls
```

By default, Spring Boot recognizes these extensions:

| Extension | Purpose |
| --- | --- |
| `.graphqls` | GraphQL SDL file |
| `.gqls` | Short extension for GraphQL SDL |

The filename does not determine the GraphQL type name. For example, `book.graphqls` can declare `Book`, `Query`, `Mutation`, or other types. Filenames and directories mainly help group resources so the development team can manage them easily.

`.graphql` or `.txt` files are not part of the default extension list. If you use other extensions, configure `spring.graphql.schema.file-extensions` accordingly.

## 3. Creating your first schema file

Create `src/main/resources/graphql/book.graphqls`:

```graphql
type Query {
  book(id: ID!): Book
  books: [Book!]!
}

type Book {
  id: ID!
  title: String!
  publishedYear: Int
}
```

This file declares the root query type and the `Book` object type. After the application starts, the GraphQL runtime schema will have the fields `Query.book`, `Query.books`, and the fields of `Book`.

The Java controller provides values for the root fields:

```java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }
}
```

The SDL file and the controller have distinct responsibilities:

- SDL defines which fields clients can call, arguments, return types, and nullability.
- `@QueryMapping` maps a Java method to a field on the root `Query`.
- Services and repositories determine how data is loaded.

Placing the file in the right classpath location only ensures the schema is loaded. It does not automatically create resolvers for fields. If the schema has `Query.book` without a matching data fetcher or property fetcher, the query may return `null` or fail depending on the field type and execution behavior.

## 4. Splitting the schema into multiple files by domain

A small schema can live in a single file. As the API grows, split the SDL by domain or type group so each file has an understandable scope.

Example:

```text
src/main/resources/graphql/
├── common/
│   └── scalars.graphqls
├── book/
│   └── book.graphqls
├── author/
│   └── author.graphqls
└── review/
    └── review.graphqls
```

`book.graphqls` defines the root query and book type:

```graphql
type Query {
  book(id: ID!): Book
  books(first: Int = 20): [Book!]!
}

type Book {
  id: ID!
  title: String!
  author: Author
}
```

`author.graphqls` adds author queries:

```graphql
extend type Query {
  author(id: ID!): Author
  authors: [Author!]!
}

type Author {
  id: ID!
  name: String!
  biography: String
}
```

`review.graphqls` declares reviews and extends the `Book` type:

```graphql
extend type Book {
  reviews: [Review!]!
}

type Review {
  id: ID!
  rating: Int!
  comment: String
}
```

Spring Boot loads the SDL resources according to the schema locations, and then GraphQL Java builds a unified schema from the type definitions and type extensions. Clients see a single GraphQL API; separate files are simply a way to organize the schema source.

### Using type extensions when adding fields

If `Query` is already defined in `book.graphqls`, another file wishing to add fields should use:

```graphql
extend type Query {
  author(id: ID!): Author
}
```

Similarly, to add fields to an existing `Book` type, use `extend type Book`.

Do not redeclare `type Query` or `type Book` in a second file just to add fields. A schema cannot have two independent type definitions with the same name. Type extensions are designed to add fields or directives to an existing type.

The extended type must exist in the schema after all resources are loaded. If you use `extend type Review` without any file defining `type Review`, schema validation will fail when building the schema.

## 5. File loading order is not a dependency mechanism

Do not design your schema assuming `book.graphqls` is always loaded before `author.graphqls` simply because of filename or directory order. SDL resources are aggregated to build the schema; express type relationships using valid definitions and extensions.

For example, `Book` references `Author` even though `Author` is defined in another file:

```graphql
type Book {
  id: ID!
  author: Author
}
```

This is valid as long as the full set of schema resources contains the `Author` definition. If that resource is not in the schema locations or is missing from the classpath, the schema cannot resolve the referenced type.

Principles when splitting files:

- Each GraphQL type has only one base definition.
- Other files use `extend type` to add fields.
- Type, field, argument, and enum value names must be consistent.
- Custom scalars must have both an SDL declaration and corresponding runtime wiring.
- Do not use filenames as namespaces; `Book` in two different directories is still the same GraphQL type name.

## 6. Configuring schema locations

You can change the default location using the `spring.graphql.schema.locations` property.

Example using a dedicated directory:

```yaml
spring:
  graphql:
    schema:
      locations:
        - classpath:api-schema/**/
```

In this case, place the SDL files in:

```text
src/main/resources/api-schema/
├── query.graphqls
└── book/
    └── book.graphqls
```

You can configure multiple locations:

```yaml
spring:
  graphql:
    schema:
      locations:
        - classpath:graphql/**/
        - classpath:shared-graphql/**/
```

This is useful when the schema is split into a shared part and an application-specific part. Every location must point to resources present on the classpath or a valid resource location that Spring can read.

### Configuring file extensions

By default, Spring Boot looks for `.graphqls` and `.gqls`. If a project wants to use another extension, you can declare:

```yaml
spring:
  graphql:
    schema:
      file-extensions:
        - .graphqls
        - .gqls
        - .graphql
```

When `.graphql` is added, files with that extension in the configured locations can also be recognized as schema resources. Standardize on one or two extensions across the project so developers can easily identify SDL files.

### Full configuration in application.yml

```yaml
spring:
  graphql:
    schema:
      locations:
        - classpath:graphql/**/
      file-extensions:
        - .graphqls
        - .gqls
    path: /graphql
```

`spring.graphql.path` is the GraphQL HTTP endpoint. It is independent of `spring.graphql.schema.locations`: one property determines where to find SDL, while the other determines the URL receiving requests.

## 7. Resources in main and test classpaths

Resources in `src/main/resources` are packaged with the application and used at runtime. Resources in `src/test/resources` are added to the classpath when running tests.

Example:

```text
src/
├── main/resources/graphql/
│   └── book.graphqls
└── test/resources/graphql/
    └── test-fixture.graphqls
```

During tests, the classpath usually contains both main and test resources. With default schema locations that scan `graphql/**/`, a test file placed under the same pattern may be loaded alongside the main schema in the test context. This can be helpful if the fixture file is part of the test schema, but causes duplicate type errors if it redefines existing types.

If you need a separate schema for tests, configure schema locations explicitly for tests or place fixtures outside the pattern scanned by the application by default. Avoid accidentally putting a second complete schema into `src/test/resources/graphql/` expecting it to replace the main schema.

Similarly, never place schemas needed for production only in `src/test/resources`; those resources are not packaged into the application artifact.

## 8. Verifying the schema is actually inside the artifact

A common mistake is an application running in the IDE but failing to find the schema when deployed. The cause is usually in the build tool's resource configuration or filenames not matching the searched extensions.

With Gradle, resources in `src/main/resources` are processed by the `main` source set and placed into the output resources. With Maven, `src/main/resources` is the default resource directory. If you customized `sourceSets`, `processResources`, or `resources` in your build, verify whether schemas are copied into the output.

When packaging a JAR, you can inspect the artifact contents using the `jar` tool:

```bash
jar tf build/libs/library-api.jar
```

With Maven, replace with the JAR path in `target/`. In the entry list, verify there are files such as:

```text
BOOT-INF/classes/graphql/book.graphqls
BOOT-INF/classes/graphql/author/author.graphqls
```

If those entries are missing, the issue lies in resource packaging before Spring GraphQL is initialized. If the files exist in the JAR yet the schema is still not loaded, double-check `spring.graphql.schema.locations` and `file-extensions`.

## 9. Loading schemas via Java configuration when customization is needed

For standard applications, use `spring.graphql.schema.locations` so Spring Boot loads classpath resources automatically. Only consider declaring your own `GraphQlSource` when you need control over schema creation, runtime wiring, or resource sources.

When an application declares its own `GraphQlSource` bean, default auto-configuration may back off because a bean of the same type is already present. The application then becomes responsible for configuring all schema resources and required runtime wiring. Avoid adding a custom `GraphQlSource` solely to change the SDL directory if configuration properties already meet your needs.

A programmatic configuration can use `GraphQlSource.schemaResourceBuilder()` and provide an explicit list of `Resource` objects. Exact syntax depends on the Spring for GraphQL version; consult the Javadoc for your exact version before customizing the builder. After creating a custom `GraphQlSource`, verify the schema, runtime wiring, scalars, type resolvers, and other components that were previously auto-configured.

## 10. Schema files and controllers use separate discovery mechanisms

Spring Boot searches for SDL resources on the classpath. Spring for GraphQL also needs to discover controllers annotated with `@Controller`, `@QueryMapping`, `@MutationMapping`, `@SubscriptionMapping`, and `@SchemaMapping`.

These two processes are independent:

| Component | Where is it discovered? | Role |
| --- | --- | --- |
| SDL schema | Classpath resources via schema locations and extensions | Defines the GraphQL contract |
| Controller/resolver | Spring application context via component scanning or bean configuration | Provides data for fields |
| Runtime wiring | `RuntimeWiringConfigurer` beans and GraphQL configuration | Registers scalars, type resolvers, or custom data fetchers |

Having a `book.graphqls` file does not mean `BookController` is automatically discovered if the controller lies outside component scan. Conversely, a controller with `@QueryMapping` cannot make a field appear in the schema if the SDL does not declare that field.

When a field is declared in the schema without a custom resolver, GraphQL can use the default property data fetcher to read the corresponding property/getter on the source object. If no matching property exists, the result may be null; for non-null fields, this can lead to an execution error.

## 11. Testing that schema files are loaded

You should have tests confirming that schema resources are found and representative operations can execute. `GraphQlTester` tests documents and responses at the GraphQL layer:

```java
@GraphQlTest(BookController.class)
class BookSchemaTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockBean
    BookService bookService;

    @Test
    void bookQueryIsAvailableInLoadedSchema() {
        graphQlTester.document("""
                query {
                    __type(name: "Query") {
                        fields {
                            name
                        }
                    }
                }
                """)
                .execute()
                .path("__type.fields[*].name")
                .entityList(String.class)
                .contains("book");
    }
}
```

This example uses introspection to verify that the `book` field exists in the runtime schema. If the application deliberately disables introspection in the test profile, test by executing an actual operation instead of querying `__type`.

You can test the operation directly:

```java
graphQlTester.document("""
        query {
            book(id: "book-1") {
                id
                title
            }
        }
        """)
    .execute()
    .path("book.id")
    .entity(String.class)
    .isEqualTo("book-1");
```

A complete test needs to mock or seed appropriate data for `BookService`. The goal is to confirm both that the SDL is loaded and that the resolver is wired to the field.

`@GraphQlTest` is suitable for slice tests of GraphQL controllers and schemas. `@SpringBootTest` is useful when you want to test full application configuration, including resource locations, component scanning, and runtime wiring beans.

## 12. Common errors when loading schemas from the classpath

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Schema not found | File is outside `classpath:graphql/**/` | Check location in `src/main/resources` and `spring.graphql.schema.locations` |
| File not loaded | Extension is not in the configured list | Check `.graphqls`, `.gqls`, and `spring.graphql.schema.file-extensions` |
| Works in IDE but fails in JAR | Build did not package SDL files | Check `build/resources/main`, `target/classes`, and JAR contents |
| `There is no type ...` or type reference error | A type is referenced without a definition in schema resources | Check loaded SDL files and type extensions |
| Duplicate type definition | Multiple files redeclare the same type instead of using `extend type` | Keep one base definition and move additions to extensions |
| Field does not exist when querying | SDL does not declare the field or file containing the field is not loaded | Inspect runtime schema via introspection or test operations |
| Field returns null despite valid SDL | Missing resolver or source object lacks matching property | Check controller mapping and property fetcher |
| Test context fails with duplicate schema | Files in `src/test/resources/graphql` loaded alongside main files | Check test resources and test schema locations |
| Custom scalar does not work | SDL has `scalar X` but runtime wiring has not registered the scalar | Check `RuntimeWiringConfigurer` |

When schema parsing or validation fails, Spring Boot usually cannot create a valid GraphQL runtime and the application may stop at startup. Read the first error in the logs because it usually points to the file, type, or field causing the issue.

## 13. Guidelines for organizing schema resources

- Place production schemas under `src/main/resources`.
- Use the default `graphql` directory unless there is a special requirement; keeping configuration simple helps newcomers find files easily.
- Split files by domain or type group, such as book, author, review.
- Use `.graphqls` or `.gqls` consistently.
- Define each type only once; use `extend type` to add fields from other files.
- Do not rely on file order or directory names to express dependencies.
- Keep SDL schemas close to the domain API and review schemas like source code.
- Verify resources are packaged in the deployment artifact.
- Avoid putting test fixture schemas in the same classpath pattern as production schemas unless intentional.
- Use a custom `GraphQlSource` only when configuration properties are insufficient.
- Test the runtime schema in CI to catch type reference, duplicate definition, and resolver mapping errors early.

## 14. Hands-on exercise

Create a schema for a library application using multiple files:

1. Create `src/main/resources/graphql/book.graphqls` containing `Query.book`, `Query.books`, and the `Book` type.
2. Create `author/author.graphqls` defining `Author` and using `extend type Query` to add author queries.
3. Create `review/review.graphqls` defining `Review` and using `extend type Book` to add the `reviews` field.
4. Write controllers for the root queries and nested field resolvers.
5. Run the application and verify a query returns data across multiple types.
6. Change the schema location to `classpath:api-schema/**/` and move the SDL files to the new directory.
7. Package the application and verify the SDL files are present in the executable JAR.
8. Write a `GraphQlTester` test confirming that fields from the author and review files exist in the runtime schema.

Once completed, make sure you can explain why SDL files must be on the classpath, which locations and extensions Spring Boot searches by default, how multiple files become a single schema, when to use `extend type`, and how to distinguish a resource-not-found error from an invalid-schema error.

## 15. References

- [Spring Boot — Spring for GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Spring for GraphQL — Schema Resources](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Boot API — GraphQlProperties.Schema](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/graphql/autoconfigure/GraphQlProperties.Schema.html)

Properties and auto-configuration packages may change between Spring Boot versions. When upgrading a project, check the reference documentation and Javadoc matching the exact version used by your dependency management.
