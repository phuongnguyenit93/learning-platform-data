# RuntimeWiringConfigurer

## Objectives

After this lesson, you will be able to:

- Explain the role of `RuntimeWiringConfigurer` in building the GraphQL runtime.
- Distinguish between SDL, `RuntimeWiring`, `DataFetcher`, and the GraphQL engine.
- Register a `DataFetcher`, custom scalar, and `TypeResolver` using `RuntimeWiringConfigurer`.
- Integrate `RuntimeWiringConfigurer` with Spring Boot's auto-configuration mechanism.
- Coordinate runtime wiring with annotated controllers without creating duplicate mappings.
- Know when to use `RuntimeWiringConfigurer` and when to use other extension points in Spring for GraphQL.

## 1. What is RuntimeWiringConfigurer?

GraphQL SDL describes the API structure: which types exist, which arguments a field accepts, and what type the result has. SDL alone does not specify how to fetch data for each field. The server needs runtime configuration to connect schema declarations with execution behavior.

In Spring for GraphQL, `RuntimeWiringConfigurer` is the extension point that allows an application to customize GraphQL Java's `RuntimeWiring.Builder`.

The interface has the following method:

~~~java
public interface RuntimeWiringConfigurer {
    void configure(RuntimeWiring.Builder builder);
}
~~~

A bean implementing this interface can register components such as:

- `DataFetcher` instances for schema fields.
- Custom scalars and data conversion rules.
- `TypeResolver` instances for interfaces or unions.
- `SchemaDirectiveWiring` for custom directives.
- `WiringFactory` to provide wiring based on schema definitions.

You can visualize the process as follows:

~~~mermaid
flowchart TD
    A[Schema SDL] --> C[GraphQlSource]
    B[RuntimeWiringConfigurer beans] --> D[RuntimeWiring.Builder]
    D --> C
    C --> E[GraphQLSchema]
    E --> F[GraphQL engine]
    F --> G[ExecutionGraphQlService]
    G --> H[HTTP / WebSocket / RSocket]
~~~

`RuntimeWiringConfigurer` is invoked when Spring builds the GraphQL schema/runtime. It is not a controller that handles individual requests. The `DataFetcher` instances registered during configuration will be used by the GraphQL engine when executing operations.

## 2. Distinguishing SDL, RuntimeWiring, and DataFetcher

These three components have distinct responsibilities:

| Component | Responsibility | Example |
|---|---|---|
| SDL | Declares the contract and data structure | `type Query { book(id: ID!): Book }` |
| RuntimeWiring | Connects the schema with execution behavior | Registers a `DataFetcher` for `Query.book` |
| DataFetcher | Retrieves the value for a field when a query runs | Calls a repository to find a `Book` |

Example SDL:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

The schema indicates that the `book` field accepts an `id` argument and returns a `Book`. The `DataFetcher` decides how to find the `Book` object for that ID.

If you only declare SDL without a `DataFetcher` or an appropriate property mapping mechanism, GraphQL can still build the schema, but fields may not return the expected data.

GraphQL Java can use the default `PropertyDataFetcher` to read properties from the source object for standard object fields. Therefore, not every field requires an explicit `DataFetcher` registration.

## 3. Creating a RuntimeWiringConfigurer bean in Spring Boot

With the Spring Boot GraphQL starter, beans of type `RuntimeWiringConfigurer` are automatically discovered and applied when building `GraphQlSource`.

Example registering a `DataFetcher` for `Query.book`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class BookRuntimeConfiguration {

    @Bean
    RuntimeWiringConfigurer bookDataFetcher(BookRepository repository) {
        return wiringBuilder -> wiringBuilder
                .type("Query", typeBuilder -> typeBuilder
                        .dataFetcher("book", environment -> {
                            String id = environment.getArgument("id");
                            return repository.findById(id).orElse(null);
                        })
                );
    }
}
~~~

Explanation:

- `@Configuration` declares a Spring configuration class.
- `@Bean` registers a `RuntimeWiringConfigurer` object in the application context.
- `type("Query", ...)` selects the GraphQL object type named `Query`.
- `dataFetcher("book", ...)` attaches the `DataFetcher` to the `Query.book` field.
- `environment.getArgument("id")` reads the argument passed by the client.
- The repository returns the `Book` object or null if not found.

Type and field names must match the SDL. If the schema renames the field to `findBook`, the wiring must also be updated accordingly.

### Using a class implementing the interface

If the configuration is complex, you can create a separate class instead of writing a lambda in the bean method:

~~~java
public class BookRuntimeWiringConfigurer
        implements RuntimeWiringConfigurer {

    private final BookRepository repository;

    public BookRuntimeWiringConfigurer(BookRepository repository) {
        this.repository = repository;
    }

    @Override
    public void configure(RuntimeWiring.Builder builder) {
        builder.type("Query", typeBuilder ->
                typeBuilder.dataFetcher("book", environment -> {
                    String id = environment.getArgument("id");
                    return repository.findById(id).orElse(null);
                })
        );
    }
}
~~~

Register this class as a bean using constructor injection. An explicit implementation class is useful when wiring covers many fields or when configuration needs to be split by domain.

## 4. Reading data from DataFetchingEnvironment

The parameter passed to a `DataFetcher` is typically `DataFetchingEnvironment`. This is the context describing the field currently being executed.

Commonly used APIs:

| API | Purpose |
|---|---|
| `getArgument("name")` | Reads an argument of the field |
| `getSource()` | Retrieves the parent object being resolved |
| `getGraphQlContext()` | Reads the shared context of the GraphQL request |
| `getLocalContext()` | Reads the local context passed from the parent field |
| `getSelectionSet()` | Checks the child fields requested by the client |
| `getField()` | Retrieves information about the current field |

For example, a nested field can read the source object from its parent field:

Suppose the schema adds an `author` field to `Book`:

~~~graphql
type Book {
  id: ID!
  authorId: ID!
  author: Author
}

type Author {
  id: ID!
  name: String!
}
~~~

~~~java
@Bean
RuntimeWiringConfigurer bookAuthorFetcher(AuthorRepository authorRepository) {
    return builder -> builder.type("Book", typeBuilder ->
            typeBuilder.dataFetcher("author", environment -> {
                Book book = environment.getSource();
                return authorRepository.findById(book.getAuthorId())
                        .orElse(null);
            })
    );
}
~~~

Here, `Book.author` is resolved based on the `Book` object returned from the parent field. The `DataFetcher` reads `authorId` and then loads the corresponding `Author`.

For Spring for GraphQL applications using annotated controllers, similar logic is typically written with `@SchemaMapping`. Choose one mechanism per field to keep configuration easy to understand and avoid duplicate mappings.

Do not store per-request data in mutable fields of a shared `RuntimeWiringConfigurer` or `DataFetcher` bean. Configuration beans are typically reused across multiple requests. Per-request data should be obtained from the environment, GraphQL context, or appropriate request-scoped mechanisms.

## 5. Registering a custom scalar

A custom scalar requires rules for parsing input and serializing output. Runtime wiring is where the scalar is registered under the corresponding name in the SDL.

Example using GraphQL Java Extended Scalars:

~~~java
import graphql.scalars.ExtendedScalars;
import org.springframework.context.annotation.Bean;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Bean
RuntimeWiringConfigurer scalarConfigurer() {
    return builder -> builder
            .scalar(ExtendedScalars.Date)
            .scalar(ExtendedScalars.DateTime);
}
~~~

SDL:

~~~graphql
scalar Date
scalar DateTime

type Appointment {
  serviceDate: Date!
  startsAt: DateTime!
}
~~~

The scalar name in the SDL must match the registered scalar. Extended Scalars `Date` typically converts to `LocalDate`, while `DateTime` typically converts to `OffsetDateTime`.

For a hand-written custom scalar, create a `GraphQLScalarType` and register it via `builder.scalar(...)`. The scalar's `Coercing` implementation must handle `serialize`, `parseValue`, and `parseLiteral` when the API supports both variables and literals.

## 6. Registering a TypeResolver for interfaces and unions

GraphQL interfaces and unions are abstract types. When a `DataFetcher` returns a Java object, GraphQL needs to determine the corresponding concrete GraphQL object type.

Example SDL:

~~~graphql
interface SearchResult {
  id: ID!
}

type Book implements SearchResult {
  id: ID!
  title: String!
}

type Author implements SearchResult {
  id: ID!
  name: String!
}

type Query {
  search: [SearchResult!]!
}
~~~

Runtime wiring can register a `TypeResolver`:

~~~java
@Bean
RuntimeWiringConfigurer searchResultTypeResolver() {
    return builder -> builder.type("SearchResult", typeBuilder ->
            typeBuilder.typeResolver(environment -> {
                Object source = environment.getObject();

                if (source instanceof BookResult) {
                    return environment.getSchema()
                            .getObjectType("Book");
                }

                if (source instanceof AuthorResult) {
                    return environment.getSchema()
                            .getObjectType("Author");
                }

                throw new IllegalStateException(
                        "Unsupported SearchResult type: "
                                + source.getClass().getName());
            })
    );
}
~~~

`TypeResolver` only determines the concrete type. It does not load data for the `title`, `name`, or `id` fields. Those fields continue to be resolved by property fetchers, `DataFetcher` instances, or annotated controller mappings.

Spring for GraphQL provides a default `ClassNameTypeResolver` mechanism that infers the GraphQL type from the class name by convention. You only need to register a custom `TypeResolver` when the default convention does not fit or the application needs explicit control over type resolution.

## 7. Registering custom directive wiring

A GraphQL directive can attach metadata or behavior to a schema element. GraphQL includes several standard directives such as `@skip`, `@include`, `@deprecated`, and `@specifiedBy`. Applications can also declare custom directives.

Example SDL:

~~~graphql
directive @uppercase on FIELD_DEFINITION

type Book {
  title: String! @uppercase
}
~~~

When you want a directive to alter how a field behaves, implement `SchemaDirectiveWiring` and register it with runtime wiring:

~~~java
@Bean
RuntimeWiringConfigurer directiveConfigurer(
        UppercaseDirectiveWiring uppercaseWiring) {

    return builder -> builder.directiveWiring(uppercaseWiring);
}
~~~

`UppercaseDirectiveWiring` is a class implemented by the application. It can intercept the field definition and its corresponding `DataFetcher` during schema construction.

Not every directive needs custom wiring. Some directives are handled natively by the GraphQL engine. Only register `SchemaDirectiveWiring` for directives defined by the application or requiring custom behavior.

## 8. Multiple RuntimeWiringConfigurers in one application

An application can have multiple `RuntimeWiringConfigurer` beans, each responsible for a part of the runtime:

~~~java
@Configuration
public class GraphQlRuntimeConfiguration {

    @Bean
    RuntimeWiringConfigurer dateScalarConfigurer() {
        return builder -> builder.scalar(ExtendedScalars.Date);
    }

    @Bean
    RuntimeWiringConfigurer dateTimeScalarConfigurer() {
        return builder -> builder.scalar(ExtendedScalars.DateTime);
    }
}
~~~

Splitting configurers gives each configuration a clear responsibility:

- One configurer registers the `Date` scalar.
- One configurer registers the `DateTime` scalar.
- One configurer registers `TypeResolver`s.
- One configurer registers `DataFetcher`s for specialized fields.
- One configurer registers directive wiring.

Spring Boot collects the configurer beans and applies them when building the GraphQL runtime. When multiple configurers affect the same type or field, check whether they are overriding or conflicting with each other's configuration. Do not rely on accidental ordering to decide which `DataFetcher` wins.

Each field should have a single primary owner for its mapping. If a field is already handled by `@QueryMapping` or `@SchemaMapping`, avoid simultaneously registering another `DataFetcher` for that same field unless there is a clear reason and you have verified how the configurations are merged.

## 9. RuntimeWiringConfigurer and annotated controllers

Spring for GraphQL supports two main styles for connecting fields to Java logic:

| Approach | When Suitable |
|---|---|
| `RuntimeWiringConfigurer` and `DataFetcher` | Need direct control over GraphQL Java runtime wiring |
| `@QueryMapping`, `@MutationMapping`, `@SchemaMapping` | Want to write resolvers using Spring's annotated controllers |

Annotated controllers are integrated by Spring through `AnnotatedControllerConfigurer`, which participates in the runtime wiring process. Consequently, with the Spring Boot starter, controllers are discovered and registered automatically.

Example controller:

~~~java
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
}
~~~

In this case, there is no need to add a `DataFetcher` for `Query.book` in another `RuntimeWiringConfigurer`.

Use `RuntimeWiringConfigurer` when you need GraphQL Java-layer integration such as custom scalars, `TypeResolver`s, or directive wiring. Use annotated controllers for business logic of `Query`, `Mutation`, and field mappings when that is the application's primary style.

If you manually build `GraphQlSource` instead of relying on auto-configuration, make sure the builder receives all required configurers, including the configurer that registers annotated controllers if you want to continue using controller mappings.

## 10. How does RuntimeWiringConfigurer differ from other extension points?

Not all GraphQL customizations belong in `RuntimeWiring`.

| Extension point | Scope |
|---|---|
| `RuntimeWiringConfigurer` | `DataFetcher`, scalars, `TypeResolver`, directive wiring, and `RuntimeWiring` components |
| `GraphQlSourceBuilderCustomizer` | Customizes the `GraphQlSource` construction process in Spring Boot |
| `Instrumentation` | Observes or intercepts GraphQL execution |
| `DataFetcherExceptionResolver` | Converts exceptions thrown by `DataFetcher` into GraphQL errors |
| `WebGraphQlInterceptor` | Processes requests/responses at the Web GraphQL transport layer |
| `@SchemaMapping` | Maps a specific field via an annotated controller |

For example, if you need to measure operation execution time or attach instrumentation to the GraphQL engine, use the instrumentation mechanism. If you need to convert exceptions into structured GraphQL error messages, use `DataFetcherExceptionResolver`.

Do not use `RuntimeWiringConfigurer` to solve a transport-layer or request-lifecycle problem.

## 11. Testing RuntimeWiringConfigurer

A configurer should be tested at two levels:

1. Whether the runtime configuration registers the right components into the schema.
2. Whether actual GraphQL operations return data and handle errors properly.

Example test using `GraphQlTester`:

~~~java
@Test
void shouldResolveBookUsingRuntimeDataFetcher() {
    graphQlTester.document("""
            query {
                book(id: "b-01") {
                    id
                    title
                }
            }
            """)
            .execute()
            .path("book.id")
            .entity(String.class)
            .isEqualTo("b-01");
}
~~~

Scenarios to verify:

- Fields with a `DataFetcher` return the expected data.
- Arguments are read with the right type and name.
- Missing IDs are handled according to SDL nullability.
- Custom scalars parse variables and serialize output in the expected format.
- `TypeResolver` selects the right concrete type for interfaces or unions.
- Custom directives take effect as described in the contract.
- No fields have duplicate mappings or unintended overrides.

Testing a lambda in isolation without initializing the GraphQL runtime can miss field name, schema, or wiring errors. Integration tests using the real SDL schema catch these issues earlier.

## 12. Common issues

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Field always returns null | Wrong type or field name in wiring | Cross-check against the SDL |
| `DataFetcher` is not invoked | Configurer not registered as a bean or source does not receive the configurer | Check the Spring application context and `GraphQlSource` |
| Custom scalar does not work | SDL and registered scalar names do not match | Check scalar name and coercing |
| Interface/union fails to resolve | Missing or incorrect `TypeResolver` | Check the Java object and GraphQL object type |
| Controller mappings do not work with a custom source | Missing `AnnotatedControllerConfigurer` | Include the controller configurer in runtime wiring |
| Results get overridden | Multiple configurers register the same field | Designate a single owner for the mapping |
| Different requests share wrong data | Per-request state stored in a shared bean | Obtain data from `DataFetchingEnvironment` or GraphQL context |

## 13. Principles for organizing RuntimeWiringConfigurer

In real-world implementations:

- Split configurers by responsibility or domain.
- Use constructor injection to provide repositories and services to `DataFetcher`s.
- Keep configurers and `DataFetcher`s free of mutable per-request state.
- Use exact GraphQL type and field names matching the SDL.
- Register custom scalars, `TypeResolver`s, and directive wiring in an easy-to-find location.
- Avoid registering two mapping mechanisms for the same field.
- Leverage annotated controllers for standard business resolvers.
- Test GraphQL operations against the real schema after configuring runtime wiring.

`RuntimeWiringConfigurer` should be viewed as the integration layer between the schema and the GraphQL Java runtime. It should not become the home for all application business logic. `DataFetcher`s should delegate to the appropriate services and let services handle domain rules.

## Conclusion

`RuntimeWiringConfigurer` is Spring for GraphQL's extension point for customizing `RuntimeWiring.Builder`. Through it, an application can register `DataFetcher`s, custom scalars, `TypeResolver`s, and custom directive wiring so GraphQL Java can execute the SDL schema.

With Spring Boot, `RuntimeWiringConfigurer` beans are discovered automatically when creating `GraphQlSource`. Annotated controllers also participate in runtime wiring via `AnnotatedControllerConfigurer`. Understanding the boundaries between these mechanisms helps you pick the right tool, avoid duplicate mappings, and keep GraphQL configuration testable and maintainable.

## References

- [Spring for GraphQL — Request Execution and Runtime Wiring](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring Boot — Spring for GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [GraphQL Java — RuntimeWiring API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/schema/idl/RuntimeWiring.html)
