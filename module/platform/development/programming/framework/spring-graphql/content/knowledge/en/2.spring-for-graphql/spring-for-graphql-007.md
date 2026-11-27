# GraphQL Schema in a Spring Application

In a Spring for GraphQL application, the schema is the contract describing what data clients can query, what arguments they can pass, and what types they receive. The schema is also the connection point between the GraphQL API and Java components: a field declared in SDL can be resolved by a controller, a `@SchemaMapping` method, a batch resolver, or the default property-reading mechanism of the source object.

Spring for GraphQL uses GraphQL Java to execute schemas and operations. With Spring Boot, applications typically declare the schema using **Schema Definition Language (SDL)** in resource files, then use Spring annotations to supply data for fields. This approach makes the API structure explicit and independent of data storage and Java class organization.

After this lesson, you will be able to organize SDL files in a Spring application, define root types and data types, understand nullable/list/input rules, load multiple schema files, map fields to controllers, and test schemas and resolvers with `GraphQlTester`.

## 1. What role does the schema play in Spring for GraphQL?

A GraphQL API has two parts that must work together:

- **Schema** describes the shape of the API: what types exist, what fields each type has, what arguments fields accept, what return types they have, and which fields allow `null`.
- **Data fetcher/resolver** provides values when GraphQL executes a field. In Spring for GraphQL, a resolver is typically a method in a `@Controller` class annotated with `@QueryMapping`, `@MutationMapping`, `@SubscriptionMapping`, `@SchemaMapping`, or `@BatchMapping`.

For example, a schema might declare `Query.book(id: ID!): Book`. This declaration states that clients can invoke the `book` field with a required ID and receive a `Book` or `null`. It does not say whether the book comes from JPA, JDBC, a REST service, or memory. The resolver implementation decides how to fetch the data.

The schema is also not an auto-generated Java DTO. You can use records, classes, interfaces, or existing domain types as source objects for resolvers, as long as the returned data is compatible with the schema. A good schema describes client needs; the Java model and database can be designed around the server's internal needs.

## 2. Creating a project and placing schema files

With Spring Boot, add the GraphQL starter and a web starter to provide an HTTP endpoint. Maven example:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-graphql</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

If the application uses Spring WebFlux, choose `spring-boot-starter-webflux` instead of `spring-boot-starter-web`. Dependency versions are typically managed by Spring Boot dependency management; do not pin a different GraphQL Java version than the compatible one Boot manages without a specific reason.

Spring Boot auto-configures `GraphQlSource` and the HTTP endpoint when it detects the matching dependencies. By default, schemas are searched under `classpath:graphql/**/` with `.graphqls` and `.gqls` extensions. A common project layout:

```text
src/
├── main/
│   ├── java/com/example/library/
│   │   ├── LibraryApplication.java
│   │   └── graphql/
│   │       ├── BookGraphQlController.java
│   │       └── AuthorGraphQlController.java
│   └── resources/
│       ├── application.properties
│       └── graphql/
│           ├── book.graphqls
│           └── author.graphqls
└── test/
    └── java/com/example/library/
        └── BookGraphQlControllerTests.java
```

You can explicitly declare schema locations and the endpoint in `application.properties`:

```properties
spring.graphql.schema.locations=classpath:graphql/**/
spring.graphql.schema.file-extensions=.graphqls,.gqls
spring.graphql.path=/graphql

# Enable the interactive playground UI only in development environments.
spring.graphql.graphiql.enabled=true
```

The first properties correspond to SDL file locations and extensions. `spring.graphql.path` sets the URL receiving GraphQL requests; `/graphql` is the common default path. GraphiQL is an interactive UI for testing queries in development and should not be enabled indiscriminately in production.

When the application runs with default settings, clients send HTTP requests to `/graphql`, typically using POST with a JSON body containing a `query` field and `variables` if needed. Declaring a schema does not generate separate REST endpoints for each type; GraphQL operations go through the shared GraphQL endpoint.

## 3. Defining root types and object types with SDL

GraphQL has three standard root types:

- `Query` describes data-reading operations.
- `Mutation` describes data-modifying operations.
- `Subscription` describes event streams clients subscribe to.

A small schema for a library system can be written as follows:

```graphql
type Query {
  book(id: ID!): Book
  books(filter: BookFilter, first: Int = 20): [Book!]!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}

type Subscription {
  bookCreated: Book!
}

type Book {
  id: ID!
  title: String!
  status: BookStatus!
  author: Author
}

type Author {
  id: ID!
  name: String!
}

enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

input BookFilter {
  keyword: String
  status: BookStatus
  authorId: ID
}

input CreateBookInput {
  title: String!
  authorId: ID!
  status: BookStatus = DRAFT
}
```

In SDL, `type Book` describes an object that can appear in responses. `Query.book` and `Query.books` are fields clients can call to read data. `Mutation.createBook` takes an input object and returns the newly created book. `Subscription.bookCreated` describes the payload of each new-book event.

If root types use the standard default names `Query`, `Mutation`, and `Subscription`, GraphQL recognizes them without requiring a `schema` block. If you want to use different root type names, declare them explicitly, for example:

```graphql
schema {
  query: LibraryQuery
  mutation: LibraryMutation
}

type LibraryQuery {
  book(id: ID!): Book
}

type LibraryMutation {
  createBook(input: CreateBookInput!): Book!
}
```

A root query is a required part of an executable GraphQL schema. Mutation and Subscription are optional depending on application needs.

## 4. Understanding scalars, enums, and custom scalars

GraphQL defines several built-in scalars:

| Scalar | Meaning |
| --- | --- |
| `Int` | Signed 32-bit integer |
| `Float` | Floating-point number |
| `String` | UTF-8 character string |
| `Boolean` | True or false value |
| `ID` | Identifier, typically passed and returned as a string |

`BookStatus` in the example is an enum. Clients can only send one of `DRAFT`, `PUBLISHED`, or `ARCHIVED`. Enums let the schema constrain the allowed value domain instead of accepting an arbitrary string. When mapping to Java, you can use a matching enum so GraphQL Java converts values accordingly.

Dates, times, currency, or specialized data types are not built-in scalars. If the API needs a type like `Date`, the application must register a custom scalar defining how to parse inputs, serialize outputs, and validate values. Spring for GraphQL allows adding runtime configuration via `RuntimeWiringConfigurer`. You can use pre-built scalars from the GraphQL Java extended scalars library or implement `GraphQLScalarType` yourself when your application format has custom rules.

For example, if you have added the `graphql-java-extended-scalars` library, you can register a date scalar:

```java
@Configuration
public class GraphQlRuntimeConfiguration {

    @Bean
    RuntimeWiringConfigurer runtimeWiringConfigurer() {
        return wiringBuilder ->
                wiringBuilder.scalar(ExtendedScalars.Date);
    }
}
```

The schema can then declare a field `publishedOn: Date`. The scalar name in SDL must match the scalar name registered in runtime wiring. Simply adding `scalar Date` to SDL is not enough for GraphQL to know how to convert date values.

## 5. Designing nullable types and lists

In GraphQL, fields are nullable by default. The `!` mark indicates a non-null field: the resolver must supply a non-null value if the operation executes that field successfully.

For lists, `!` can be applied independently to the list itself and to each element:

| Type | Can the list be null? | Can an element be null? |
| --- | --- | --- |
| `[Book]` | Yes | Yes |
| `[Book]!` | No | Yes |
| `[Book!]` | Yes | No |
| `[Book!]!` | No | No |

For example, `books: [Book!]!` requires the resolver to return a non-null list containing no `null` elements. An empty list `[]` is still valid. Meanwhile, `book(id: ID!): Book` allows a not-found result to be `null`.

When a resolver returns `null` for a non-null field, GraphQL produces an error and propagates `null` up to the nearest nullable parent field. Therefore, deciding to add `!` is part of API contract design, not merely a type annotation. Use non-null when the application can guarantee that value in every valid scenario.

## 6. Distinguishing object types and input types

`type` describes data the server can return. `input` describes structures clients can pass into arguments. These two categories cannot be used interchangeably.

For example, `Book` is an object type used in responses, while `CreateBookInput` is an input type used for mutations:

```graphql
type Book {
  id: ID!
  title: String!
  author: Author!
}

input CreateBookInput {
  title: String!
  authorId: ID!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
```

An input object can only contain scalars, enums, or other input objects, optionally combined with lists and non-null modifiers. It cannot contain an output object type like `Author` or `Book`, nor can it declare fields with resolvers like an object type. If you need to reference an existing object, pass its ID or a dedicated input object.

In Java, an input object can be bound to a record or class:

```java
public record CreateBookInput(
        String title,
        String authorId,
        BookStatus status) {
}
```

Spring for GraphQL supports binding arguments into Java objects. Field names and types in the input must match the constructor/properties of the class or record. If inputs are nested, design matching Java types and validate required data at the appropriate layer.

## 7. Mapping root fields to Spring controllers

Once SDL is in place, controllers supply data for root fields. Spring for GraphQL uses `@Controller` to discover handler methods. Dedicated annotations specify which root type's field a method handles.

```java
@Controller
public class BookGraphQlController {

    private final BookService bookService;

    public BookGraphQlController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }

    @QueryMapping
    public List<Book> books(
            @Argument("filter") BookFilter filter,
            @Argument("first") Integer first) {
        return bookService.search(filter, first);
    }

    @MutationMapping
    public Book createBook(
            @Argument("input") CreateBookInput input) {
        return bookService.create(input);
    }
}
```

Because the method names `book`, `books`, and `createBook` match the field names in the schema, Spring can infer the mapped field. You can specify a different name in the annotation, such as `@QueryMapping(name = "findBook")`, if the Java method name differs from the SDL field. `@Argument` extracts values from field arguments; argument names must match the schema or be specified explicitly in the annotation.

`@QueryMapping` corresponds to fields on the `Query` root type, `@MutationMapping` to the `Mutation` root type, and `@SubscriptionMapping` to the `Subscription` root type. These annotations are specialized, readable shorthands for declaring `@SchemaMapping` on the corresponding root type.

A subscription example can return a reactive stream:

```java
@Controller
public class BookSubscriptionController {

    private final BookEventService eventService;

    public BookSubscriptionController(BookEventService eventService) {
        this.eventService = eventService;
    }

    @SubscriptionMapping
    public Flux<Book> bookCreated() {
        return eventService.bookCreated();
    }
}
```

`Flux<Book>` emits a `Book` for each event. Clients need a transport that supports subscriptions along with the matching server configuration. Merely declaring `type Subscription` in SDL does not create an event source; the resolver must return a publisher capable of emitting data.

## 8. Mapping nested fields with @SchemaMapping

An object type often has fields referencing other objects. For example, `Book.author` returns an `Author`. If this field is not an existing property on the source object, write a resolver for it using `@SchemaMapping`.

```java
@Controller
public class BookFieldController {

    private final AuthorService authorService;

    public BookFieldController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }
}
```

`typeName = "Book"` identifies the object type in SDL, and `field = "author"` identifies the field to resolve. The `Book book` parameter is the source object received from the parent field. The return value must be compatible with the `Author` type in the schema.

If the `Book` DTO already has a matching `author` property or getter, GraphQL Java can use the default property data fetcher to read that value without needing a `@SchemaMapping` method. Write a dedicated resolver when you need computation, another service call, data-loading control, or model transformation.

### Batching field resolution with @BatchMapping

When a query returns many books and each book needs the `author` field, a simple resolver may call the service to fetch the author separately for each book. If each call executes a database query, the number of queries grows with the number of books and creates the N+1 problem.

`@BatchMapping` lets Spring for GraphQL group source objects and resolve the field in a batch. For example:

```java
@Controller
public class BookBatchController {

    private final AuthorService authorService;

    public BookBatchController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        Set<String> authorIds = books.stream()
                .map(Book::authorId)
                .collect(Collectors.toSet());

        Map<String, Author> authorsById =
                authorService.findAllByIds(authorIds);

        return books.stream().collect(Collectors.toMap(
                Function.identity(),
                book -> authorsById.get(book.authorId())
        ));
    }
}
```

The example assumes the service returns a map of authors keyed by ID. In real applications, decide how to handle missing IDs and ensure map keys match the source objects. Use `@BatchMapping` in place of a single-item `@SchemaMapping` resolver for the same field; do not register two competing resolvers for the same field.

The schema still declares `Book.author` as a normal field. Batching is a server-side implementation detail; clients do not need to know whether a field is resolved one object at a time or in batches.

## 9. Splitting schemas across multiple files

As the API grows, you can split schemas by domain or feature group, such as `book.graphqls`, `author.graphqls`, and `review.graphqls`. Spring Boot finds the files in schema locations and GraphQL Java builds a unified schema from those definitions.

If one file already declares `type Query`, another file wanting to add fields to Query should use `extend type Query`:

```graphql
# book.graphqls
type Query {
  book(id: ID!): Book
  books: [Book!]!
}

type Book {
  id: ID!
  title: String!
}
```

```graphql
# author.graphqls
extend type Query {
  author(id: ID!): Author
  authors: [Author!]!
}

type Author {
  id: ID!
  name: String!
}
```

`extend type Query` extends the existing root type. If you declare `type Query` again as a new definition instead of an extension, the schema may fail with a duplicate definition error. Type names, fields, arguments, and enum values must remain consistent across all loaded files.

Splitting files makes source management easier, while clients still see a single unified API schema. File names do not create GraphQL namespaces; two files both defining `Book` do not become two different types just because they live in separate files.

## 10. Adding runtime wiring when the schema needs special configuration

SDL describes types and fields, but certain types need runtime behavior to convert values or determine concrete types. Spring for GraphQL provides `RuntimeWiringConfigurer` to add GraphQL Java configuration, such as custom scalars, type resolvers for interfaces/unions, or specialized data fetchers.

The `Date` custom scalar example earlier was registered via `RuntimeWiringConfigurer`. For interfaces or unions, GraphQL needs to identify the concrete object type when a resolver returns an instance. If default resolution rules are insufficient, you can register an appropriate `TypeResolver` in runtime wiring.

Do not put heavy business logic in runtime wiring. Data reads/writes, authorization checks, or service calls belong in controllers, services, or specialized components. Runtime wiring is meant for schema-level execution configuration.

## 11. Verifying schemas and resolvers with GraphQlTester

Once the schema is loaded and controllers are registered, test real operations rather than only testing individual Java methods. `GraphQlTester` lets you send a GraphQL document, pass variables, and assert response values by field path.

```java
@GraphQlTest(BookGraphQlController.class)
class BookGraphQlControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockBean
    BookService bookService;

    @Test
    void returnsBookById() {
        given(bookService.findById("book-42"))
                .willReturn(new Book("book-42", "Introduction to GraphQL"));

        graphQlTester.document("""
                query FindBook($id: ID!) {
                    book(id: $id) {
                        id
                        title
                    }
                }
                """)
                .variable("id", "book-42")
                .execute()
                .path("book.id")
                .entity(String.class)
                .isEqualTo("book-42");
    }
}
```

This is a condensed example; the `Book` type, constructor, and mock setup should match the actual application. `@GraphQlTest` focuses on GraphQL components and the specified controllers. If you want to verify the entire application configuration, schema, transport, and security chain, use `@SpringBootTest` with the appropriate tester.

Include tests for the following cases:

- Valid queries return the expected fields and data types.
- Missing required arguments or arguments of invalid types.
- Mutations accept input objects and return the expected results.
- Nested fields resolve properly, including batch resolvers if present.
- Nullable fields return `null` as contracted; non-null fields do not unexpectedly return `null`.
- Resolver errors are represented properly in the `errors` section of the response.

## 12. Common errors when integrating schemas with Spring

| Symptom | Common cause | What to check |
| --- | --- | --- |
| Schema not found or empty | File placed in wrong directory, wrong extension, or mismatched schema locations config | Check `src/main/resources/graphql/`, `spring.graphql.schema.locations`, and `spring.graphql.schema.file-extensions` |
| Parse or validation error on startup | Invalid SDL syntax, reference to nonexistent type, or duplicate definitions | Read the schema error, inspect types/fields and `extend` files |
| `Cannot query field ...` | Query requests a field not present on the type in the schema | Compare the document with the loaded SDL |
| Resolver not invoked | Wrong root type, field name, or `typeName` in mapping | Compare `@QueryMapping`, `@MutationMapping`, `@SchemaMapping` with SDL |
| Argument receives `null` | Wrong argument name, incompatible type, or client did not send the variable | Check `@Argument`, name in SDL, and variables payload |
| Object field returns `null` unexpectedly | Property fetcher cannot find property or resolver returns no data | Check getters/properties on source object and mapping method |
| Custom scalar fails to parse | Scalar declared in SDL without registering coercing/runtime wiring | Register the matching scalar and check input/output formats |
| Schema error when splitting across multiple files | Multiple files redefine the same type instead of extending the existing type | Use `extend type` and avoid duplicate field definitions |

## 13. Schema design principles for Spring applications

- Design the schema around domain language and client needs. Do not let database table structure dictate the entire API directly.
- Use dedicated `input` types for mutations and filters. Do not reuse output types as inputs just to save lines of SDL.
- Choose nullable/non-null based on actual data guarantees of the system. Changing a field from nullable to non-null can impact existing clients.
- Name fields and arguments consistently. Use client-side aliases when a different response field name is needed, rather than creating multiple server fields solely for one screen's naming preference.
- Split SDL into multiple files by domain when needed, while maintaining one unified schema and using `extend type` to add root fields.
- Keep resolvers thin: accept arguments, call the appropriate service, and return the result. Business rules belong in the service/domain layer.
- Monitor how many times resolvers are invoked. Use `@BatchMapping` or DataLoader when nested fields risk causing N+1 queries.
- Protect data on the server. A field appearing in the schema does not mean every user is allowed to read or modify it; enforce authentication and authorization at the appropriate operation/field level.
- Test schemas and responses using operations representative of clients, especially when adding fields, changing nullability, or modifying input types.

## 14. Practice exercise

Extend the library API according to the following requirements:

1. Create `book.graphqls` with `Query.book`, `Query.books`, `Mutation.createBook`, `Book`, `Author`, `BookStatus`, and the required input types.
2. Split author declarations into `author.graphqls`, using `extend type Query` to add `author(id: ID!): Author`.
3. Write `@QueryMapping` for book queries and `@MutationMapping` for creating a book.
4. Write `@SchemaMapping` for `Book.author`. Then replace it with `@BatchMapping` when querying a list of many books to reduce service calls.
5. Write `GraphQlTester` tests for fetching a single book, fetching a list of books, and creating a book via mutation.

A core portion of the SDL can start like this:

```graphql
type Query {
  book(id: ID!): Book
  books(first: Int = 20): [Book!]!
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}

type Book {
  id: ID!
  title: String!
  author: Author
}

input CreateBookInput {
  title: String!
  authorId: ID!
}
```

When finished, verify that every field in your operations exists in the schema, every root field has a matching handler or property fetcher, inputs bind to the proper Java types, and responses conform to the declared nullability. This is the foundation for learning error handling, field-level security, DataLoader, and query optimization in Spring for GraphQL.
