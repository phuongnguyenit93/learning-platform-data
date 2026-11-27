# GraphQlSourceBuilder in Spring for GraphQL

## Objectives

After this lesson, you will be able to:

- Explain the role of `GraphQlSource` and its builder in initializing the GraphQL runtime.
- Distinguish between schema construction and executing individual GraphQL requests.
- Know how to load one or more SDL files into `GraphQlSource`.
- Combine `RuntimeWiringConfigurer` to register DataFetchers, scalars, and type resolvers.
- Understand the steps when calling `build()` and the resulting runtime produced.
- Distinguish between `GraphQlSource.Builder`, `GraphQlSourceBuilderCustomizer`, and `RuntimeWiringConfigurer`.
- Customize the builder in Spring Boot while preserving auto-configuration.
- Recognize the impact of declaring a custom `GraphQlSource` bean and replacing the default configuration.
- Test the schema, runtime wiring, and diagnose initialization errors.

## 1. What is GraphQlSource?

`GraphQlSource` is the Spring for GraphQL abstraction representing the GraphQL runtime built from the schema and runtime wiring. It provides the ready-to-use GraphQL object for accepting operations through Spring GraphQL's execution layer.

To create `GraphQlSource`, the application needs to combine components such as:

- SDL schemas describing types, fields, arguments, inputs, enums, interfaces, and unions.
- Runtime wiring connecting schema fields to DataFetchers, scalars, type resolvers, and other execution components.
- Extensions for error handling, instrumentation, and runtime customizations if needed by the application.

You can visualize the relationships between these components as follows:

~~~mermaid
flowchart TD
    A["Schema SDL resources"] --> D["GraphQlSource builder"]
    B["RuntimeWiringConfigurer"] --> D
    C["Exception resolvers / Instrumentation"] --> D
    D --> E["build()"]
    E --> F["GraphQlSource"]
    F --> G["ExecutionGraphQlService"]
    G --> H["GraphQL request execution"]
~~~

The builder gathers configuration during initialization. After calling `build()`, the application receives `GraphQlSource` for components such as `ExecutionGraphQlService` to use when handling requests.

It is important to distinguish two phases:

- **Build time:** reading SDL, building the schema, applying runtime wiring, and constructing the GraphQL runtime.
- **Request time:** each GraphQL operation is fed into the pre-built runtime to be parsed, validated, and executed.

Do not recreate `GraphQlSource` on every request. The schema and runtime wiring are typically built once during application context initialization and then reused.

## 2. What does the GraphQlSource builder handle?

The builder assembles the GraphQL runtime step by step, rather than requiring the application to construct every GraphQL Java object manually.

A configuration typically needs to decide:

1. Which SDL sources are used to build the schema?
2. Which `RuntimeWiringConfigurer` beans need to be applied?
3. Which DataFetchers and type resolvers connect to fields or abstract types?
4. Which custom scalars are registered?
5. Which exception resolvers and instrumentation need to be integrated?
6. Once configuration is complete, how is the runtime built and exposed as a bean?

Exact API names may vary across Spring GraphQL versions. In Spring for GraphQL, the common entry point for building from schema files is `GraphQlSource.schemaResourceBuilder()`. The returned builder supports declaring schema resources, configuring runtime wiring, and building `GraphQlSource`.

The lesson title `GraphQlSourceBuilder` refers to the family of builder APIs used to create `GraphQlSource`. In Spring GraphQL code, the common entry points are `GraphQlSource.schemaResourceBuilder()` and related builder interfaces; when using Spring Boot, you also have the `GraphQlSourceBuilderCustomizer` extension point. Do not confuse an initialization-time builder with a request-handling service.

Minimal example:

~~~java
GraphQlSource graphQlSource = GraphQlSource.schemaResourceBuilder()
        .schemaResources(
                new ClassPathResource("graphql/schema.graphqls")
        )
        .build();
~~~

This example shows the basic structure: select the resource containing the SDL, then call `build()`. In a real application, runtime wiring must be added so that business fields have appropriate DataFetchers.

## 3. Loading SDL schemas into the builder

The schema can be placed in one or more resources. Example:

~~~text
src/main/resources/
└── graphql/
    ├── schema.graphqls
    ├── book.graphqls
    └── author.graphqls
~~~

Multiple resources can be passed into the builder:

~~~java
@Bean
GraphQlSource graphQlSource() {
    return GraphQlSource.schemaResourceBuilder()
            .schemaResources(
                    new ClassPathResource("graphql/schema.graphqls"),
                    new ClassPathResource("graphql/book.graphqls"),
                    new ClassPathResource("graphql/author.graphqls")
            )
            .build();
}
~~~

Definitions across multiple files are combined into a single GraphQL schema. Splitting files helps organize the schema by business domain, but all types and fields must still form a valid schema once merged.

Example root file containing root types:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

The `book.graphqls` file can add fields using `extend`:

~~~graphql
type Book {
    id: ID!
    title: String!
}

extend type Query {
    books: [Book!]!
}
~~~

If multiple files define the same type or field in an invalid way, schema construction can fail. Use `extend` when adding to an existing type and validate the combined schema.

### 3.1. Resource paths and classpath

`ClassPathResource` loads files from the application's classpath. When packaged as a JAR, resources must be included inside the artifact so the builder can read them at startup.

If the schema resides on the filesystem or another resource source, use an appropriate `Resource` implementation. Avoid hard-coding developer machine paths if the application needs to run across multiple environments.

In Spring Boot, schema location properties are usually sufficient to configure where SDL files are found. You only need to specify resources explicitly in the builder when the application actively manages `GraphQlSource` itself or has special requirements.

## 4. How is runtime wiring applied?

SDL describes the contract, but it does not itself supply data for fields. Runtime wiring connects fields in the schema with execution components.

Spring for GraphQL provides `RuntimeWiringConfigurer`, an extension point that allows adding configuration to `RuntimeWiring.Builder`.

Manual DataFetcher example:

~~~java
@Component
class BookDataFetcher implements DataFetcher<Book> {

    private final BookService bookService;

    BookDataFetcher(BookService bookService) {
        this.bookService = bookService;
    }

    @Override
    public Book get(DataFetchingEnvironment environment) {
        String id = environment.getArgument("id");
        return bookService.findById(id);
    }
}
~~~

Registering the DataFetcher:

~~~java
@Bean
RuntimeWiringConfigurer bookRuntimeWiring(BookDataFetcher bookDataFetcher) {
    return wiringBuilder -> wiringBuilder
            .type("Query", typeWiring -> typeWiring
                    .dataFetcher("book", bookDataFetcher));
}
~~~

In this example:

- `Query` is the root object type in the SDL.
- `book` is the field connected to the DataFetcher.
- `environment.getArgument("id")` retrieves the argument sent by the client.
- The DataFetcher returns the value for the `book` field.

Type and field names must match the SDL. If a field is undeclared or misspelled, schema wiring cannot create the intended mapping.

### 4.1. How does RuntimeWiringConfigurer differ from builder customizers?

These extension points are related but have different responsibilities:

| Component | Role |
| --- | --- |
| `RuntimeWiringConfigurer` | Configures GraphQL runtime wiring: DataFetchers, scalars, type resolvers, and related wiring |
| `GraphQlSourceBuilderCustomizer` | Customizes the builder used to create `GraphQlSource` in Spring Boot |
| `GraphQlSource.Builder` | Builder API for declaring schema resources and configuring source creation |
| `GraphQlSource` | The built runtime source used by the execution layer |

If you only need to add a DataFetcher or scalar, you should typically register a `RuntimeWiringConfigurer`. There is no need to rebuild `GraphQlSource` manually just to add a field mapping.

## 5. Registering multiple runtime components

A GraphQL runtime may require multiple `RuntimeWiringConfigurer` beans. For example:

- One configurer registers DataFetchers for `Query`.
- One configurer registers custom scalars.
- One configurer registers type resolvers for interfaces or unions.
- One configurer registers wiring for custom directives.

Example scalar registration:

~~~java
@Bean
RuntimeWiringConfigurer scalarConfigurer() {
    return builder -> builder.scalar(ExtendedScalars.UUID);
}
~~~

Example union resolver registration:

~~~java
@Bean
RuntimeWiringConfigurer searchResultConfigurer() {
    ClassNameTypeResolver resolver = new ClassNameTypeResolver();
    resolver.addMapping(BookView.class, "Book");
    resolver.addMapping(AuthorView.class, "Author");

    return builder -> builder.type(
            "SearchResult",
            type -> type.typeResolver(resolver)
    );
}
~~~

Spring Boot collects `RuntimeWiringConfigurer` beans and applies them while building `GraphQlSource`. This lets each functional area contribute configuration without cramming everything into one massive class.

When multiple configurers affect the same type or field, ensure they do not unintentionally override or conflict with each other. If order matters, use Spring's supported ordering mechanisms and test the final wiring result.

## 6. Exception resolvers and instrumentation

The builder is also where components affecting execution are integrated.

### 6.1. DataFetcherExceptionResolver

DataFetchers can throw exceptions when calling services or accessing data. `DataFetcherExceptionResolver` enables mapping exceptions into structured GraphQL errors.

Example resolver bean:

~~~java
@Component
class BookExceptionResolver extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable exception,
            DataFetchingEnvironment environment) {

        if (exception instanceof BookNotFoundException) {
            return GraphqlErrorBuilder.newError(environment)
                    .message("Book not found")
                    .errorType(ErrorType.NOT_FOUND)
                    .build();
        }

        return null;
    }
}
~~~

In a Spring Boot application, exception resolvers are integrated via the corresponding GraphQL configuration. When manually constructing `GraphQlSource`, ensure the necessary resolvers are supplied to the builder using the API of the version in use.

Do not turn every exception into the same generic business error. Distinguish between not-found, validation, authorization, and infrastructure errors so responses and logs remain meaningful.

### 6.2. Instrumentation

GraphQL Java provides `Instrumentation` to observe or intercept the GraphQL execution lifecycle—for instance, recording timing, tracking activity, or enforcing runtime policies.

Example instrumentation use cases:

- Measuring operation execution time.
- Collecting metrics by operation name.
- Tracking errors and execution status.
- Recording data for tracing.
- Integrating query complexity limits or analysis when an appropriate implementation exists.

Instrumentation must be chosen carefully because it can run on every request. Avoid logging raw documents and variables verbatim if they might contain tokens or sensitive data.

The builder supports integrating instrumentation according to the GraphQL Java/Spring GraphQL API for your version. In a Boot application, prefer the extension points supported by your Boot version instead of manually creating the source just to attach an instrumentation.

## 7. Creating GraphQlSource manually

In some applications that do not use auto-configuration or need full control over the GraphQL runtime, you can declare a `GraphQlSource` bean using the builder.

Example:

~~~java
@Configuration
class ManualGraphQlSourceConfiguration {

    @Bean
    GraphQlSource graphQlSource(BookDataFetcher bookDataFetcher) {
        return GraphQlSource.schemaResourceBuilder()
                .schemaResources(
                        new ClassPathResource("graphql/schema.graphqls")
                )
                .configureRuntimeWiring(builder -> builder
                        .type("Query", type -> type
                                .dataFetcher("book", bookDataFetcher)))
                .build();
    }
}
~~~

This is a minimal manual assembly example. When managing the source yourself, the application is responsible for providing all required wiring: the annotated controller configurer if using `@QueryMapping`/`@SchemaMapping`, scalars, type resolvers, exception resolvers, instrumentation, and any other extensions the system needs.

If the application uses Spring Boot, registering your own `GraphQlSource` bean typically causes auto-configuration to back off because the default bean has been replaced. Other foundational beans may still exist, but the custom source must be configured to use them properly.

Therefore, only build the source manually when you truly need control over runtime construction. For typical needs, let Boot create `GraphQlSource` and add specialized configurers or customizers.

## 8. GraphQlSourceBuilderCustomizer in Spring Boot

Spring Boot provides `GraphQlSourceBuilderCustomizer` so applications can adjust the builder before `GraphQlSource` is created.

Example:

~~~java
import graphql.scalars.ExtendedScalars;
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class GraphQlSourceCustomization {

    @Bean
    GraphQlSourceBuilderCustomizer uuidSourceCustomizer() {
        return builder -> builder.configureRuntimeWiring(
                wiringBuilder -> wiringBuilder.scalar(ExtendedScalars.UUID)
        );
    }
}
~~~

The customizer receives the builder used by auto-configuration and adds configuration to it. Spring Boot continues to manage building the source according to the overall configuration.

However, if the goal is solely to register a scalar, a `RuntimeWiringConfigurer` bean usually expresses the responsibility more clearly:

~~~java
@Bean
RuntimeWiringConfigurer uuidScalarConfigurer() {
    return builder -> builder.scalar(ExtendedScalars.UUID);
}
~~~

Choose `GraphQlSourceBuilderCustomizer` when you need builder-level changes, such as configuring schema resources or a builder option that a runtime wiring configurer cannot express. Choose `RuntimeWiringConfigurer` for pure runtime wiring changes.

The exact API of the customizer and builder depends on the Spring Boot/Spring GraphQL version. Check the API signatures in your project version before using additional methods.
## 9. SchemaFactory and advanced schema handling

In cases where the schema must be built using special rules, the builder can be configured with a schema factory appropriate to the API version in use.

A schema factory can be useful when an application needs to:

- Combine or transform schema definitions through a custom pipeline.
- Apply shared schema construction rules.
- Integrate a schema source managed outside the classpath.
- Control `GraphQLSchema` creation before the GraphQL runtime is built.

Do not choose a schema factory just to add a DataFetcher or scalar. Those needs are already covered by `RuntimeWiringConfigurer`.

If the schema is generated dynamically from external metadata, control the data source, stability, and refresh timing. Changing the runtime schema while the application is serving requests requires a clear synchronization strategy; do not mutate a shared schema arbitrarily.

## 10. Builder lifecycle and one-time configuration

The builder is a temporary configuration object during initialization. Once `build()` is called, the result is the constructed `GraphQlSource`.

A typical lifecycle:

1. Spring initializes configuration and configurer beans.
2. Auto-configuration or application configuration creates the builder.
3. The builder receives schema resources.
4. Runtime wiring configurers are applied.
5. Required extensions are connected.
6. `build()` produces `GraphQlSource`.
7. The execution service uses the source to execute requests.

Do not hold onto the builder in a singleton and mutate configuration per request. Doing so can cause inconsistent shared state or race conditions.

If the application needs to update the schema at runtime, design a controlled refresh workflow and construct a new source via a supported mechanism. Do not modify a builder or runtime schema currently in use by concurrent requests.

## 11. Testing GraphQlSource and runtime wiring

`GraphQlSource` can be tested at multiple levels.

### 11.1. Testing the generated schema

Verify that the schema contains the expected types and fields:

~~~java
@Test
void graphQlSourceContainsBookType() {
    GraphQlSource source = graphQlSource();

    assertThat(source.schema().getObjectType("Book"))
            .isNotNull();
}
~~~

This example illustrates schema verification. In real tests, retrieve the bean from the Spring test context or create the source through the factory/configuration under test.

### 11.2. Testing runtime wiring via operations

Testing execution is usually more valuable than merely checking that a bean exists:

~~~java
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
        .path("book.title")
        .entity(String.class)
        .isEqualTo("Spring GraphQL");
~~~

This test verifies that the schema, DataFetcher or controller mapping, and execution pipeline are connected properly.

### 11.3. Testing error conditions

Tests should cover:

- Missing SDL resource.
- Invalid SDL syntax or invalid type definitions.
- Fields lacking a DataFetcher or matching property.
- Unregistered scalars.
- `TypeResolver` failing to determine the object type.
- Exception resolvers mapping errors properly.
- Instrumentation being invoked without unexpectedly altering the response.

For errors occurring during context initialization, inspect the root cause in the exception chain and condition report rather than looking only at the generic message saying the application failed to start.

## 12. Common issues

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `GraphQlSource` fails to initialize | Missing SDL resource or invalid schema | Check resource paths and parse/validation errors |
| Field exists in SDL but resolver does not run | Runtime wiring has not registered the DataFetcher/controller mapping | Check `RuntimeWiringConfigurer` and the annotated controller configurer |
| Custom scalar reports unknown type or coercion error | Scalar not declared or not registered properly | Check SDL and runtime wiring |
| Union/interface fails to resolve object type | Missing or incorrect `TypeResolver` | Check class-to-type mappings |
| Boot does not create the default source | Application registered its own `GraphQlSource` bean | Check bean overrides and manual configuration |
| A configurer has no effect | Configurer is not Spring-managed or not passed to the builder | Check bean registration and custom source setup |
| Multi-file schema fails | Duplicate definitions or improper use of `extend` | Inspect the combined schema after merging |
| Runtime behaves differently across environments | Different resources or dependencies | Check artifacts, classpath, and effective configuration |
| Modifying builder during requests causes errors | Shared mutable builder or unsynchronized refresh | Only build the source at startup or use a dedicated refresh workflow |

## 13. Process for choosing an extension point

When you need to customize the GraphQL runtime, choose the extension point based on the need:

| Need | Component to Use |
| --- | --- |
| Add a manual DataFetcher | `RuntimeWiringConfigurer` |
| Add a custom scalar | `RuntimeWiringConfigurer` |
| Map an interface or union | `RuntimeWiringConfigurer` |
| Customize how `GraphQlSource` is built in Boot | `GraphQlSourceBuilderCustomizer` |
| Manage schema resources and runtime manually | `GraphQlSource.schemaResourceBuilder()` |
| Handle errors from DataFetchers | `DataFetcherExceptionResolver` |
| Observe the GraphQL execution lifecycle | GraphQL Java `Instrumentation` |
| Implement field business logic | `@QueryMapping`, `@MutationMapping`, `@SchemaMapping` |

A practical rule of thumb is to pick the narrowest extension point that meets the requirement. This keeps configuration readable, avoids unnecessarily replacing default infrastructure, and reduces the risk of missing components already integrated by Spring Boot.

## 14. Summary

`GraphQlSource` represents the GraphQL runtime built from SDL, runtime wiring, and related extensions. The builder loads schema resources and applies DataFetchers, scalars, type resolvers, exception resolvers, and instrumentation before creating the source with `build()`.

In Spring Boot applications, prefer `RuntimeWiringConfigurer` for DataFetchers and scalars, `GraphQlSourceBuilderCustomizer` for builder customizations, and let auto-configuration create the default `GraphQlSource`. Only construct the source manually when you need full control over runtime assembly and have ensured all required configurers are wired. Testing with real GraphQL operations confirms that the schema and wiring work together as expected.

