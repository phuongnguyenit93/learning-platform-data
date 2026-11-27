# GraphQlSourceBuilderCustomizer in runtime wiring

`GraphQlSourceBuilderCustomizer` is a Spring Boot extension point that allows adding configuration to the `GraphQlSource` builder during application startup. Within the scope of runtime wiring, the customizer is useful when you need to register scalars, type resolvers, data fetchers, or schema inspection while still letting Spring Boot manage the creation of `GraphQlSource`.

An important distinction is that the customizer runs during the GraphQL runtime construction phase, not on every request. It adjusts the builder before the schema and runtime are built. When only `RuntimeWiring` configuration is needed, `RuntimeWiringConfigurer` is usually the more direct extension point; a customizer fits when that configuration needs to be combined with other capabilities of `GraphQlSource.Builder`.

## 1. Where does runtime wiring fit in the initialization process?

GraphQL SDL describes types, fields, arguments, and relationships between types. However, SDL does not contain Java implementations to resolve fields. Runtime wiring connects the schema with execution components such as data fetchers, custom scalars, directive wiring, and type resolvers.

When using the Spring Boot starter, the initialization flow can be visualized as follows:

~~~mermaid
flowchart TD
    A[Spring Boot starts] --> B[GraphQl auto-configuration]
    B --> C[Load SDL resources]
    C --> D[Create GraphQlSource builder]
    D --> E[Apply RuntimeWiringConfigurer beans]
    E --> F[Apply GraphQlSourceBuilderCustomizer beans]
    F --> G[Build GraphQlSource]
    G --> H[Create ExecutionGraphQlService]
    H --> I[Handle GraphQL operations]
~~~

The diagram illustrates the general flow. Wiring and customizer beans are collected by Spring Boot from the application context and applied to the builder before the source is built. `GraphQlSourceBuilderCustomizer` lets you influence the builder at this stage without rewriting the entire auto-configuration.

## 2. What is GraphQlSourceBuilderCustomizer?

It is a Spring Boot functional interface. The callback method receives `GraphQlSource.SchemaResourceBuilder`, which is a builder specialized for reading schema resources and inherits the common configurations of `GraphQlSource.Builder`.

With Spring Boot 3.x, import the interface from the package:

~~~java
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
~~~

Minimal bean example:

~~~java
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GraphQlRuntimeConfiguration {

    @Bean
    GraphQlSourceBuilderCustomizer runtimeWiringCustomizer() {
        return builder -> {
            // Add builder-level runtime configuration here.
        };
    }
}
~~~

With Spring Boot 4.x, the interface package changes to:

~~~java
import org.springframework.boot.graphql.autoconfigure.GraphQlSourceBuilderCustomizer;
~~~

Use the package corresponding to the Spring Boot version in your project. The callback API still works with Spring for GraphQL's builder, but do not copy Boot 3 imports into a Boot 4 project or vice versa.

The customizer should only configure the builder inside the callback. Do not call `build()` inside the callback, do not retain the builder to modify it after the application context has initialized, and do not perform per-request work here.

## 3. Configuring runtime wiring with a customizer

`GraphQlSource.Builder` provides `configureRuntimeWiring(...)` to add a `RuntimeWiringConfigurer`. You can use this API from the customizer:

~~~java
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GraphQlRuntimeConfiguration {

    @Bean
    GraphQlSourceBuilderCustomizer runtimeWiringCustomizer() {
        return builder -> builder.configureRuntimeWiring(wiring -> {
            // Configure scalar, type resolver, or data fetcher.
        });
    }
}
~~~

The `wiring` callback parameter is GraphQL Java's `RuntimeWiring.Builder`. Here you can register scalars, type resolvers, data fetchers, and other runtime components. Referenced types and fields must exist in the final SDL schema.

In applications that only need runtime wiring, a `RuntimeWiringConfigurer` bean is usually easier to read and has clearer responsibility. A customizer is valuable when you need to combine wiring with a schema factory, instrumentation, exception resolvers, schema inspection, or other builder configurations.

## 4. Registering a custom scalar

A practical example is the `DateTime` scalar. GraphQL has no built-in date/time scalar, so the SDL must declare the scalar and runtime wiring must provide the corresponding coercing implementation.

SDL:

~~~graphql
scalar DateTime

type Query {
    serverTime: DateTime!
}
~~~

Use GraphQL Java Extended Scalars to provide the implementation:

~~~java
import graphql.scalars.ExtendedScalars;
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
GraphQlSourceBuilderCustomizer dateTimeScalarCustomizer() {
    return builder -> builder.configureRuntimeWiring(wiring ->
            wiring.scalar(ExtendedScalars.DateTime)
    );
}
~~~

When a client sends or receives a `DateTime` value, the scalar implementation is responsible for parsing input and serializing output. The scalar name in the SDL must match the registered scalar name. For an application-defined scalar, implement `GraphQLScalarType` and `Coercing` with complete `parseValue`, `parseLiteral`, and `serialize` methods.

If the application only needs to register a scalar, you can use `RuntimeWiringConfigurer`:

~~~java
import graphql.scalars.ExtendedScalars;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Bean
RuntimeWiringConfigurer dateTimeRuntimeWiringConfigurer() {
    return wiring -> wiring.scalar(ExtendedScalars.DateTime);
}
~~~

Do not register the same scalar in both places. Duplicate declarations or configuring two different implementations for the same name can lead to conflicts or unpredictable behavior when building the schema.

## 5. Configuring TypeResolver for interfaces and unions

When a schema field returns an interface or union, the GraphQL runtime needs to know the concrete object type of the Java value to execute inline fragments. If default inference rules are insufficient, you can register a `TypeResolver` in runtime wiring.

Example SDL:

~~~graphql
interface SearchResult {
    id: ID!
    title: String!
}

type Book implements SearchResult {
    id: ID!
    title: String!
    isbn: String!
}

type Article implements SearchResult {
    id: ID!
    title: String!
    source: String!
}

type Query {
    search: [SearchResult!]!
}
~~~

Suppose the Java model uses classes `BookView` and `ArticleView`, which do not share the same names as the GraphQL object types. You can map them explicitly using `ClassNameTypeResolver`:

~~~java
public record BookView(String id, String title, String isbn) {}

public record ArticleView(String id, String title, String source) {}
~~~

~~~java
import graphql.schema.TypeRuntimeWiring;
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.graphql.execution.ClassNameTypeResolver;

@Bean
GraphQlSourceBuilderCustomizer searchTypeResolverCustomizer() {
    ClassNameTypeResolver typeResolver = new ClassNameTypeResolver();
    typeResolver.addMapping(BookView.class, "Book");
    typeResolver.addMapping(ArticleView.class, "Article");

    return builder -> builder.configureRuntimeWiring(wiring ->
            wiring.type(TypeRuntimeWiring.newTypeWiring("SearchResult")
                    .typeResolver(typeResolver))
    );
}
~~~

If the Java class name already matches the GraphQL object type and Spring for GraphQL's default resolver can determine the concrete type, no custom mapping is required. For unions, register a type resolver under the union name just as with interfaces.

## 6. Registering a data fetcher for a specific field

Runtime wiring also allows attaching a data fetcher directly to a field. This is useful for computed fields or fields that do not warrant a separate annotated controller method.

SDL:

~~~graphql
type Book {
    id: ID!
    title: String!
    displayLabel: String!
}
~~~

Data fetcher for `Book.displayLabel`:

~~~java
import graphql.schema.DataFetcher;
import graphql.schema.TypeRuntimeWiring;
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
GraphQlSourceBuilderCustomizer bookDisplayLabelCustomizer() {
    DataFetcher<String> displayLabelFetcher = environment -> {
        BookView book = environment.getSource();
        return book.title() + " (" + book.id() + ")";
    };

    return builder -> builder.configureRuntimeWiring(wiring ->
            wiring.type(TypeRuntimeWiring.newTypeWiring("Book")
                    .dataFetcher("displayLabel", displayLabelFetcher))
    );
}
~~~

The data fetcher receives `DataFetchingEnvironment`; `getSource()` returns the parent object being resolved. Ensure the actual source has the type expected by the fetcher. If a field has complex business logic, data access, or authorization, invoke a dedicated service rather than placing all logic inside the lambda.

Do not register the same field data fetcher in multiple places—for example, using both `@SchemaMapping` and manual wiring for the same `Book.displayLabel`. Pick one mechanism to own the field so later configuration does not overwrite earlier configuration.

## 7. Combining customizers with schema inspection

As a schema grows, some fields may lack a resolver or have a data fetcher registered under the wrong name. `inspectSchemaMappings(...)` helps inspect the relationship between the schema and mappings while creating `GraphQlSource`.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
GraphQlSourceBuilderCustomizer schemaInspectionCustomizer() {
    Logger logger = LoggerFactory.getLogger("GraphQlSchemaInspection");
    return builder -> builder.inspectSchemaMappings(report ->
            logger.info("GraphQL schema mapping report: {}", report)
    );
}
~~~

Schema inspection can point out unmapped fields or registrations that do not match the schema. It is a diagnostic aid for catching configuration issues; it does not replace business tests, access control checks, or request performance measurements.

## 8. Configuring GraphQL runtime beyond runtime wiring

`GraphQlSourceBuilderCustomizer` receives a broader builder than `RuntimeWiring.Builder`. Consequently, beyond wiring, you can combine other GraphQL runtime configurations when needed.

| Need | Appropriate Configuration Area |
| --- | --- |
| Scalars, directives, type resolvers, data fetchers | `configureRuntimeWiring(...)` |
| GraphQL Java instrumentation | `instrumentation(...)` or equivalent builder configuration |
| Changing how the GraphQL schema is created | `schemaFactory(...)` |
| Adjusting `GraphQL.Builder` | `configureGraphQl(...)` |
| Handling exceptions from data fetchers | `exceptionResolvers(...)` |
| Handling exceptions from subscription publishers | `subscriptionExceptionResolvers(...)` |
| Inspecting schema and data fetcher mappings | `inspectSchemaMappings(...)` |

For example, if you need to attach instrumentation to observe execution, configure it on the builder instead of embedding timing logic into every resolver. Instrumentation must be compatible with the GraphQL Java version managed by Spring Boot.

## 9. Ordering multiple customizers and wiring conflicts

An application can declare multiple `GraphQlSourceBuilderCustomizer` beans. Spring Boot collects them in bean order and applies them to the builder before building `GraphQlSource`. If one customizer depends on another, express the order using `@Order` or `Ordered`.

~~~java
import graphql.scalars.ExtendedScalars;
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.core.annotation.Order;

@Bean
@Order(10)
GraphQlSourceBuilderCustomizer scalarCustomizer() {
    return builder -> builder.configureRuntimeWiring(wiring ->
            wiring.scalar(ExtendedScalars.DateTime)
    );
}

@Bean
@Order(20)
GraphQlSourceBuilderCustomizer inspectionCustomizer() {
    return builder -> builder.inspectSchemaMappings(report ->
            logger.info("Schema report: {}", report)
    );
}
~~~

Customizers should be independent whenever possible. `@Order` should only be used when order genuinely matters; it does not resolve conflicts if two callbacks register or override the same scalar/data fetcher. With separate `RuntimeWiringConfigurer` beans as well, establish explicit ordering if needed and avoid implicit dependence on registration order.

If a configuration is registered both as a `RuntimeWiringConfigurer` bean and inside a customizer, check for duplication. Spring Boot already collects configurer beans through auto-configuration; you do not need to re-register them in a customizer unless you are explicitly managing the source builder yourself.

## 10. Comparing RuntimeWiringConfigurer and GraphQlSourceBuilderCustomizer

Both extension points can affect runtime wiring, but their scope and intent differ:

| Criterion | `RuntimeWiringConfigurer` | `GraphQlSourceBuilderCustomizer` |
| --- | --- | --- |
| Target | Configures `RuntimeWiring.Builder` | Customizes the `GraphQlSource` builder |
| Scope | Scalars, data fetchers, directives, type resolvers | Runtime wiring plus schema factory, instrumentation, GraphQL builder, schema inspection, and other settings |
| Focus | Focused solely on wiring | Focused on the `GraphQlSource` construction process |
| When to use | Need to register resolvers or scalars | Need to combine multiple configuration areas of `GraphQlSource` |
| With Boot starter | Declare a bean for auto-configuration to collect | Declare a bean for auto-configuration to invoke when building the source |

For instance, registering only a scalar should use `RuntimeWiringConfigurer`:

~~~java
import graphql.scalars.ExtendedScalars;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Bean
RuntimeWiringConfigurer dateTimeConfigurer() {
    return wiring -> wiring.scalar(ExtendedScalars.DateTime);
}
~~~

If you need to register a scalar and enable schema inspection at the same time, you can use a customizer:

~~~java
@Bean
GraphQlSourceBuilderCustomizer graphQlSourceCustomizer() {
    return builder -> {
        builder.configureRuntimeWiring(wiring ->
                wiring.scalar(ExtendedScalars.DateTime)
        );
        builder.inspectSchemaMappings(report -> logger.info("{}", report));
    };
}
~~~

Choosing the extension point by configuration scope keeps the application context easier to understand and reduces the chance of registering the same setting in multiple places.

## 11. Interaction with Spring Boot auto-configuration

Spring Boot creates a default `GraphQlSource` when no bean of the same type already exists. When declaring a `GraphQlSourceBuilderCustomizer`, the application still lets Boot create the source, and the customizer is invoked while preparing the builder.

If you declare your own `GraphQlSource` bean, default auto-configuration may back off. In that case, a customizer meant for the default source's builder does not automatically take over configuring your custom source. The application must ensure the custom source includes all schema resources, runtime wiring, controller configurers, scalars, type resolvers, and other required components.

Therefore, if your goal is only to add runtime wiring, prefer a `RuntimeWiringConfigurer` or `GraphQlSourceBuilderCustomizer` bean within the auto-configuration flow. Only build `GraphQlSource` yourself when you genuinely need full control over the entire build step.

## 12. Testing customizers

Customizers run when the application context starts up. The best test is to verify that the final configuration is present in the schema/runtime and that actual operations work.

Example test verifying a custom scalar is registered:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.execution.GraphQlSource;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class GraphQlRuntimeCustomizerTests {

    @Autowired
    GraphQlSource graphQlSource;

    @Test
    void registersDateTimeScalar() {
        assertThat(graphQlSource.schema().getType("DateTime"))
                .isNotNull();
    }
}
~~~

The test requires `scalar DateTime` in the SDL and a customizer or configurer bean registering `ExtendedScalars.DateTime`. Checking the schema only confirms the type exists; add `GraphQlTester` tests to verify parsing variables, parsing literals, and serializing responses.

For data fetchers or type resolvers, execute a query containing the corresponding field and assert the result by concrete type. When testing customizer ordering, you can use a test context with beans annotated with different `@Order` values and verify the resulting configuration.

Cases to cover:

1. The customizer is discovered and invoked when the context starts.
2. Scalars can parse input and serialize output.
3. Interfaces or unions resolve to the expected GraphQL object type.
4. Custom data fetchers are invoked for the right fields.
5. Schema inspection detects mismatched mappings as expected.
6. Multiple customizers execute in the declared order.
7. When a custom `GraphQlSource` bean exists, the source still has all necessary wiring.

## 13. Common issues

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Customizer is not called | Bean is not in the application context or uses the wrong Boot package | Check component scan, `@Bean`, and package for the Boot version |
| Scalar is in SDL but does not work | `GraphQLScalarType` was not registered | Add the implementation through runtime wiring |
| Interface/union fails to resolve | Missing or incorrect type resolver | Configure `TypeResolver` and concrete class mappings |
| Annotation resolver does not run | Controller configurer missing from runtime wiring | Check `AnnotatedControllerConfigurer` and the configurers applied by Boot |
| Field has two data fetchers | Same field registered via both annotation and manual wiring | Designate one owner for the mapping |
| Configuration gets overwritten | Multiple configurers/customizers modify the same type or field | Remove duplicate registrations and declare explicit ordering |
| Builder method does not exist | Spring for GraphQL version does not support the API being called | Check dependency management and the Javadoc for the exact version |
| Customizer has no effect on custom source | Application replaced the auto-configured `GraphQlSource` | Move configuration into the custom source's builder or use auto-configuration |

When investigating, check whether the application context contains the customizer bean, then verify the callback is invoked, and finally verify `GraphQlSource` and live operations. This isolates bean registration issues, builder issues, and field execution issues.

## 14. Process for applying GraphQlSourceBuilderCustomizer

When customizing the GraphQL runtime in Spring Boot:

1. Determine whether the configuration belongs to runtime wiring or the overall `GraphQlSource` builder.
2. If you only need scalars, data fetchers, directives, or type resolvers, consider `RuntimeWiringConfigurer` first.
3. If you need to combine wiring with schema inspection, instrumentation, or the GraphQL builder, declare a `GraphQlSourceBuilderCustomizer` bean.
4. Use the package corresponding to Spring Boot 3.x or 4.x.
5. Avoid registering the same scalar or data fetcher across multiple extension points.
6. Declare `@Order` if customizers have ordering dependencies.
7. Test the final schema/runtime with `GraphQlSource` and execute operations with `GraphQlTester`.

`GraphQlSourceBuilderCustomizer` helps extend the GraphQL runtime construction step while keeping Spring Boot in charge of `GraphQlSource`'s lifecycle. When scoped appropriately and coordinated clearly with `RuntimeWiringConfigurer`, applications can configure schemas and resolvers centrally without coupling controllers or services to GraphQL initialization details.

## References

- [Spring Boot 3.5 — GraphQlSourceBuilderCustomizer API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/graphql/GraphQlSourceBuilderCustomizer.html)
- [Spring Boot 4.x — GraphQlSourceBuilderCustomizer API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/graphql/autoconfigure/GraphQlSourceBuilderCustomizer.html)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — GraphQlSource API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/GraphQlSource.html)
- [GraphQL Java — Runtime Wiring](https://www.graphql-java.com/documentation/schema/)
