# When to use manual wiring

## 1. What is runtime wiring?

The SDL schema describes the GraphQL contract: which types exist, which fields each type has, which arguments are accepted, and what data types are returned. However, SDL does not contain Java logic to fetch data, call services, convert scalars, or determine the actual object type of a union. When executing an operation, GraphQL needs to know how to connect declarations in the schema with handling components on the server. That configuration process is called **runtime wiring**.

In GraphQL Java, runtime wiring is built via `RuntimeWiring`. It can register:

- `DataFetcher`s for fields to provide data when a field is executed.
- `TypeResolver`s for interfaces and unions to determine the concrete object type.
- Custom scalars to parse inputs and serialize outputs.
- Directive wiring or other GraphQL Java extension components.

With Spring for GraphQL, applications usually do not need to build the entire `RuntimeWiring` manually. Spring provides `RuntimeWiringConfigurer` to add configuration during schema creation. This is the appropriate extension point when programmatic wiring is needed instead of relying solely on controller annotations.

## 2. When should you use manual wiring?

Spring for GraphQL supports two common ways to connect schema fields with Java:

1. **Annotation-based mapping:** using `@QueryMapping`, `@MutationMapping`, `@SubscriptionMapping`, and `@SchemaMapping` on controllers.
2. **Programmatic runtime wiring:** registering `DataFetcher`s, `TypeResolver`s, scalars, and other configurations via `RuntimeWiringConfigurer`.

Annotation mapping is usually easy to read and fits business controllers well. Manual wiring is useful when:

- You want to register a `DataFetcher` using a lambda or reusable object.
- You need to configure a type resolver for an interface or union.
- You need to register a custom scalar or GraphQL Java runtime component.
- You have a schema generated or structured in a special way and need centralized wiring control.
- You want to integrate a GraphQL Java component that is not directly expressed via controller annotations.

Do not move every field to manual wiring just because you can. Pick the mapping approach that fits the application's structure and keep a single clear owner responsible for each field. Avoid registering the same field via both an annotated controller and a manual `DataFetcher`, as configuration order and field ownership become hard to trace.

## 3. `RuntimeWiringConfigurer` in Spring Boot

`RuntimeWiringConfigurer` is a Spring for GraphQL functional interface. A bean implementing this interface receives `RuntimeWiring.Builder` and registers the needed components.

Example registering a `DataFetcher` for the `Query.book` field:

SDL schema:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
```

Java configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlRuntimeConfig {

    @Bean
    RuntimeWiringConfigurer bookRuntimeWiring(BookService bookService) {
        return wiringBuilder -> wiringBuilder.type(
            "Query",
            typeWiring -> typeWiring.dataFetcher(
                "book",
                environment -> {
                    String id = environment.getArgument("id");
                    return bookService.findById(id).orElse(null);
                }
            )
        );
    }
}
```

Spring Boot detects the `RuntimeWiringConfigurer` bean and applies it while building GraphQL runtime wiring. `wiringBuilder.type("Query", ...)` selects the `Query` object type; `dataFetcher("book", ...)` registers the handler function for the `book` field.

`BookService` is a service provided by the application. Spring manages dependencies and injects the service into the bean factory method. Thus, the `DataFetcher` can invoke the business layer directly without creating services itself or accessing the database from GraphQL configuration.

If the application already uses Spring Boot auto-configuration, declaring a `RuntimeWiringConfigurer` bean is usually sufficient. There is no need to create `GraphQlSource` manually just to add a data fetcher.

## 4. Reading data from `DataFetchingEnvironment`

A `DataFetcher` receives a `DataFetchingEnvironment`. This object contains the context of the field currently being executed, such as arguments, the source object, the GraphQL context, locale, and selection set information.

| API | Purpose |
| --- | --- |
| `getArgument("name")` | Reads an argument of the current field |
| `getSource()` | Retrieves the parent object currently being resolved |
| `getGraphQlContext()` | Accesses the shared context in GraphQL execution |
| `getLocalContext()` | Accesses the local context passed from the parent field |
| `getLocale()` | Retrieves the execution locale |
| `getSelectionSet()` | Inspects the child fields requested by the client |
| `getDataLoader("name")` | Retrieves a registered DataLoader by name |

Example reading an argument:

```java
DataFetcher<Book> bookFetcher = environment -> {
    String id = environment.getArgument("id");
    return bookService.findById(id).orElse(null);
};
```

Example using the source object to resolve a nested field:

```java
DataFetcher<Author> authorFetcher = environment -> {
    Book book = environment.getSource();
    return authorService.findById(book.authorId()).orElse(null);
};
```

When the `author` field executes inside a `Book`, `getSource()` returns the parent `Book` object. The data fetcher can use the foreign key to load the corresponding `Author`.

The GraphQL context can contain data placed into the execution context by the application, such as a correlation ID or tenant information:

```java
String tenantId = environment.getGraphQlContext().get("tenantId");
```

Context does not appear automatically simply because a resolver calls `getGraphQlContext()`. The application must populate that data at request ingestion or via an appropriate context mechanism. Do not place sensitive data into the context unnecessarily, and never treat the presence of a value in the context as a substitute for permission checks.

## 5. Registering a DataFetcher for nested fields

Manual wiring is not limited to root `Query` or `Mutation` fields. You can register data fetchers for fields on object types:

SDL:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    author: Author
}

type Author {
    id: ID!
    name: String!
}
```

Runtime wiring:

```java
@Bean
RuntimeWiringConfigurer bookFieldWiring(
        BookService bookService,
        AuthorService authorService) {

    return wiringBuilder -> wiringBuilder
        .type("Query", typeWiring -> typeWiring.dataFetcher(
            "book",
            environment -> {
                String id = environment.getArgument("id");
                return bookService.findById(id).orElse(null);
            }
        ))
        .type("Book", typeWiring -> typeWiring.dataFetcher(
            "author",
            environment -> {
                Book book = environment.getSource();
                return authorService.findById(book.authorId()).orElse(null);
            }
        ));
}
```

In this example, the `Query.book` data fetcher loads the book, while the `Book.author` data fetcher uses the source object to load the author. Type and field names in `type(...)` must match the SDL schema.

For simple fields that can be read directly from a Java object's property or getter, GraphQL Java can use the default property data fetcher. Only register a dedicated data fetcher when a field requires logic, aggregated data, service calls, or non-default access.

## 6. Wiring scalars and type resolvers

### Registering custom scalars

Custom scalars must be registered with runtime wiring so GraphQL Java knows how to parse inputs and serialize outputs. You can use `RuntimeWiringConfigurer`:

```java
import graphql.scalars.ExtendedScalars;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class ScalarRuntimeConfig {

    @Bean
    RuntimeWiringConfigurer scalarWiring() {
        return wiringBuilder -> wiringBuilder
            .scalar(ExtendedScalars.Date)
            .scalar(ExtendedScalars.UUID);
    }
}
```

The SDL must declare scalars whose names match the registered implementations:

```graphql
scalar Date
scalar UUID

type Book {
    id: UUID!
    publishedOn: Date!
}
```

This example assumes the `graphql-java-extended-scalars` dependency has been added with a version compatible with the GraphQL Java version managed by Spring Boot. If writing your own scalar, register a `GraphQLScalarType` built with `Coercing` instead of the extended scalars.

### Registering TypeResolver for unions

For interfaces or unions, GraphQL needs to determine the concrete object type of a Java value at runtime. Example SDL:

```graphql
union SearchResult = Book | Author

type Query {
    search(term: String!): [SearchResult!]!
}

type Book {
    id: ID!
    title: String!
}

type Author {
    id: ID!
    name: String!
}
```

You can register a `TypeResolver`:

```java
@Bean
RuntimeWiringConfigurer searchResultWiring() {
    return wiringBuilder -> wiringBuilder.type(
        "SearchResult",
        typeWiring -> typeWiring.typeResolver(environment -> {
            Object value = environment.getObject();

            if (value instanceof Book) {
                return environment.getSchema().getObjectType("Book");
            }
            if (value instanceof Author) {
                return environment.getSchema().getObjectType("Author");
            }

            throw new IllegalStateException(
                "Unsupported SearchResult type: " + value.getClass().getName()
            );
        })
    );
}
```

`environment.getObject()` is the Java instance returned by the data fetcher. `TypeResolver` must return a `GraphQLObjectType` that exists in the schema and is a valid member of the union. If the Java value does not match any supported type, raise a clear error instead of picking an incorrect object type.

## 7. DataFetchers can return asynchronous results

GraphQL Java allows a data fetcher to return a value directly or a supported asynchronous type, such as `CompletionStage`. This is useful when a resolver calls an asynchronous service or a non-blocking HTTP client.

Example:

```java
import java.util.concurrent.CompletionStage;

DataFetcher<CompletionStage<Book>> bookFetcher = environment -> {
    String id = environment.getArgument("id");
    return bookService.findByIdAsync(id);
};
```

`findByIdAsync` is an assumed method returning `CompletionStage<Book>`. The GraphQL engine waits for the result to complete before continuing to build the response. Do not wrap a blocking call in `CompletableFuture.supplyAsync` just to make the signature look asynchronous; that still occupies a thread while waiting and can put pressure on thread pools.

If the service uses blocking JPA/JDBC, organize execution and threading consistently with the current stack. If the application uses a reactive stack, keep the reactive pipeline end-to-end instead of mixing in uncontrolled blocking operations.

## 8. Combining manual wiring with DataLoader

When a nested field's data fetcher loads one record per parent object, the application can hit the N+1 problem. Manual wiring does not solve this automatically. You can use DataLoader to coalesce requests into batches.

Example of a data fetcher retrieving a registered DataLoader:

```java
DataFetcher<CompletionStage<Author>> authorFetcher = environment -> {
    Book book = environment.getSource();
    DataLoader<String, Author> loader = environment.getDataLoader("authorLoader");
    return loader.load(book.authorId());
};
```

The DataLoader named `authorLoader` must be registered in the execution context. With Spring for GraphQL, `BatchLoaderRegistry` is the built-in mechanism for registering per-request batch loaders. The loader name, key type, and result type must match between registration and `getDataLoader`.

This example only illustrates connecting a `DataFetcher` to a `DataLoader`; it does not replace batch loader registration. Verify that the batch loader returns results in order matching the key list, handles missing keys, and does not share request caches across users with different permission contexts.

## 9. Manual wiring and annotation controllers

Both mechanisms can supply data fetchers to the GraphQL engine, but they organize code differently.

| Criterion | Annotation mapping | Manual runtime wiring |
| --- | --- | --- |
| Declaration | Annotations on controller methods | `RuntimeWiringConfigurer` and `DataFetcher` |
| Best suited for | Business-oriented controller resolvers | Shared components or specialized GraphQL Java config |
| Dependency access | Constructor injection into controller | Spring injection into configurer bean or fetcher factory |
| Nested fields | `@SchemaMapping` | `type("Book", ...).dataFetcher("author", ...)` |
| Scalars and `TypeResolver` | Can be configured via runtime wiring | Registered directly on the builder |
| Readability | Aligned with controller structure | Centralized by schema type |

Annotation mapping example:

```java
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
}
```

The equivalent programmatic mapping was registered earlier in `RuntimeWiringConfigurer`. For a given field, choose one mapping approach as the primary source. You can combine both in the same application for different fields while avoiding duplicate field registrations across multiple configurers or controllers.

## 10. When do you need to build GraphQlSource yourself?

In a standard Spring Boot application, auto-configuration creates `GraphQlSource`, loads schema resources, and applies the `RuntimeWiringConfigurer` beans provided by the application. Therefore, registering a `RuntimeWiringConfigurer` bean is enough for most additional wiring needs.

Only consider taking manual control of `GraphQlSource` creation when the application has special requirements, such as:

- Using a different set of schema resources from the default configuration.
- Needing deep customization of the schema parsing or construction pipeline.
- Integrating a custom-generated schema or coordinating multiple schema sources.
- Needing to replace part of auto-configuration with explicit application configuration.

When creating `GraphQlSource` yourself, the application must ensure both schema resources and runtime wiring are completely configured. Check the documentation for your exact Spring for GraphQL version to choose the right builder API, as builder signatures can change between versions. Do not create a custom `GraphQlSource` bean just to add a simple data fetcher, as doing so may bypass or disable parts of auto-configuration that the application relies on.

## 11. Common errors with manual wiring

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Field has no data fetcher | Type or field name in wiring does not match SDL | Cross-check `typeName` and field name in the schema |
| `DataFetcher` is not called | Configurer not discovered by Spring or schema source skips that configurer | Check bean registration and `GraphQlSource` configuration |
| Field always returns `null` | `getSource()` or argument has wrong type, or service finds no data | Check source object, arguments, and service output |
| Argument type-casting error | Java type does not match scalar coercion | Use a compatible Java type and test inputs |
| Union/interface fails to resolve | Missing `TypeResolver` or invalid object type returned | Register a `TypeResolver` for the abstract type and cover all implementations |
| Custom scalar reports parse/serialize error | Scalar not registered or format is inconsistent | Check SDL, runtime wiring, and coercing |
| Field mapped in multiple places | Both an annotated controller and a manual `DataFetcher` exist for the same field | Choose one owner for the field and remove the redundant mapping |
| DataLoader returns data out of order | Batch loader does not align results with the key list | Ensure results align per key or use a mapped batch loader |
| Application fails to start after custom `GraphQlSource` | Custom config lacks schema resources or runtime components | Check schema creation and consider keeping auto-configuration |

## 12. Testing runtime wiring

Test against the real schema and operations rather than merely checking that the `RuntimeWiringConfigurer` bean was created.

Example using `GraphQlTester` to confirm a manual data fetcher works:

```java
@SpringBootTest
@AutoConfigureHttpGraphQlTester
class ManualWiringTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void bookFieldIsResolvedByRuntimeWiring() {
        graphQlTester.document("""
            query {
                book(id: "book-42") {
                    id
                    title
                }
            }
            """)
            .execute()
            .path("book.id")
            .entity(String.class)
            .isEqualTo("book-42");
    }
}
```

The example assumes the test context configures `BookService` or matching test data. Beyond the response, verify:

- The schema exposes the fields and data types declared in the SDL.
- `DataFetcher` receives the expected arguments and source objects.
- Scalars parse input and serialize output according to the defined format.
- `TypeResolver` recognizes every implementation of interfaces/unions.
- DataLoader batches keys and returns proper results when multiple parent objects exist.
- Service errors are translated into GraphQL errors per application policy.

If using multiple `RuntimeWiringConfigurer` beans, include integration tests confirming all configurations are applied together without overlapping field registrations.

## 13. Checklist before using manual wiring

- [ ] Clearly identify why runtime wiring is needed instead of annotation mapping.
- [ ] SDL declares the types and fields to be wired.
- [ ] A `RuntimeWiringConfigurer` bean is discovered by Spring.
- [ ] Type and field names in wiring match the schema.
- [ ] `DataFetcher` handles arguments, source object, and context properly.
- [ ] Business dependencies are injected via Spring rather than instantiated inside the fetcher.
- [ ] Custom scalars and `TypeResolver`s are registered if required by the schema.
- [ ] No field is mapped twice across multiple mechanisms.
- [ ] N+1 risks are evaluated and DataLoader is registered if batch loading is needed.
- [ ] Operations are tested through `GraphQlTester` with realistic data or appropriate fixtures.
- [ ] `GraphQlSource` is created manually only for special configuration needs and verified against the exact version's API.

## Conclusion

Manual wiring lets you connect fields in a GraphQL schema to `DataFetcher`s, `TypeResolver`s, custom scalars, and GraphQL Java runtime components. In Spring for GraphQL, `RuntimeWiringConfigurer` is the standard extension point for registering those components while still leveraging Spring Boot's `GraphQlSource` creation process.

Use annotation mapping for resolvers tied directly to business controllers, and use manual wiring when lower-level GraphQL Java configuration is required. For each field, designate a single clear mapping mechanism, verify type/field names, manage dependencies through Spring, and test operations after schema initialization. This keeps runtime wiring clear, maintainable, and compatible with features such as scalars, union/interface resolvers, and DataLoaders.
