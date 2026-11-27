# GraphQlSourceBuilderCustomizer in the Spring Boot Starter

`GraphQlSourceBuilderCustomizer` is a Spring Boot extension point for applications that need to customize the creation of `GraphQlSource`. Spring Boot uses `GraphQlSource` to provide the GraphQL runtime configured from SDL schemas, runtime wiring, and execution components. By declaring a `GraphQlSourceBuilderCustomizer` bean, an application can add configuration to the builder while keeping the starter's default auto-configuration flow.

Customizers are commonly used to register custom scalars, configure schema inspection, adjust how the schema is built, add type visitors, or configure `GraphQL.Builder`. This lesson explains where customizers fit in the initialization process, how to write the bean, how they work alongside `RuntimeWiringConfigurer`, and what to check when upgrading Spring Boot.

## 1. What Is GraphQlSource?

Spring for GraphQL uses `GraphQlSource` as an abstraction to supply the built `graphql.GraphQL` instance and `GraphQLSchema`. The schema describes the API structure in SDL; runtime wiring connects schema fields to their corresponding data fetchers, custom scalars, type resolvers, and directives.

In a Spring Boot application using `spring-boot-starter-graphql`, auto-configuration typically creates the foundational components:

1. Locate and read `.graphqls` or `.gqls` schema files.
2. Create the `GraphQlSource` builder and apply property configuration.
3. Detect beans such as `RuntimeWiringConfigurer`, `Instrumentation`, `DataFetcherExceptionResolver`, and `SubscriptionExceptionResolver`.
4. Apply any declared `GraphQlSourceBuilderCustomizer` beans.
5. Build `GraphQlSource`, then use it to configure `ExecutionGraphQlService`.

~~~mermaid
flowchart TD
    A[Spring Boot application starts] --> B[GraphQlAutoConfiguration]
    B --> C[Load SDL resources]
    C --> D[Create GraphQlSource builder]
    D --> E[Apply GraphQL properties]
    E --> F[Apply RuntimeWiringConfigurer beans]
    F --> G[Apply GraphQlSourceBuilderCustomizer beans]
    G --> H[Build GraphQlSource]
    H --> I[Create ExecutionGraphQlService]
    I --> J[GraphQL requests can be executed]
~~~

The diagram shows the high-level auto-configuration startup flow. Exact bean details and application order may vary across Spring Boot versions; check the API of the version in use when relying on ordering across multiple customizers.

## 2. What Problems Does GraphQlSourceBuilderCustomizer Solve?

Normally, an application only needs to declare SDL in `src/main/resources/graphql` and write controllers with `@QueryMapping`, `@MutationMapping`, or `@SchemaMapping`. Spring Boot automatically discovers controllers and registers handler methods as data fetchers.

Some requirements demand deeper configuration, such as:

- The schema uses application-defined scalars such as `DateTime` or `Money`.
- You need to customize how GraphQL Java generates execution IDs or configure `GraphQL.Builder`.
- You want to enable schema mapping inspection to catch fields without resolvers.
- You need to configure a default `TypeResolver` for interfaces or unions.
- You need to add a `GraphQLTypeVisitor` to inspect or modify the code registry after the schema is built.
- You need a custom schema factory, such as when combining schemas from multiple sources or implementing federation.

`GraphQlSourceBuilderCustomizer` grants access to the builder during auto-configuration to perform these customizations. It is a startup-time callback, not a per-request GraphQL interceptor.

## 3. Declaring Your First Customizer

This is a functional interface, so it can be implemented as a class or a lambda. In Spring Boot 3.x, the interface's package is `org.springframework.boot.autoconfigure.graphql`:

~~~java
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GraphQlConfiguration {

    @Bean
    GraphQlSourceBuilderCustomizer graphQlSourceBuilderCustomizer() {
        return builder -> {
            // Customize GraphQlSource builder here.
        };
    }
}
~~~

The `customize(...)` method receives the builder Spring Boot is using to create `GraphQlSource`. The application simply adds the needed configuration to this builder. Do not call `build()` inside the customizer, because Spring Boot still needs to apply other customizers before finishing `GraphQlSource` creation.

In Spring Boot 3.5, the callback parameter type is `GraphQlSource.SchemaResourceBuilder`. This builder reads schema resource files and inherits shared configuration methods from `GraphQlSource.Builder`.

## 4. Registering a Custom Scalar Using a Customizer

A common example is a schema requiring a `DateTime` scalar. GraphQL has built-in scalars such as `Int`, `Float`, `String`, `Boolean`, and `ID`; date/time types are not part of the default scalar set. We can use the GraphQL Java Extended Scalars library to provide parsing and serialization.

### 4.1. Declaring the Scalar in SDL

~~~graphql
scalar DateTime

type Query {
    serverTime: DateTime!
}
~~~

### 4.2. Adding the Extended Scalars Library

Add the `com.graphql-java:graphql-java-extended-scalars` dependency to the project. If the project uses Spring Boot dependency management, let the BOM manage a compatible version or select an Extended Scalars version compatible with the GraphQL Java version managed by Spring Boot.

### 4.3. Configuring the Scalar with GraphQlSourceBuilderCustomizer

~~~java
import graphql.scalars.ExtendedScalars;
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GraphQlScalarConfiguration {

    @Bean
    GraphQlSourceBuilderCustomizer dateTimeScalarCustomizer() {
        return builder -> builder.configureRuntimeWiring(runtimeWiring ->
                runtimeWiring.scalar(ExtendedScalars.DateTime)
        );
    }
}
~~~

`configureRuntimeWiring(...)` lets you configure `RuntimeWiring.Builder`. Calling `scalar(...)` registers the scalar implementation so GraphQL Java knows how to convert values between GraphQL and Java. The scalar name in SDL must match the scalar registered in runtime wiring.

Controllers can return a Java type supported by the scalar, such as `OffsetDateTime` for the corresponding `DateTime` scalar:

~~~java
import java.time.OffsetDateTime;

import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class TimeController {

    @QueryMapping
    public OffsetDateTime serverTime() {
        return OffsetDateTime.now();
    }
}
~~~

The scalar is responsible for serializing return values and parsing inputs if the scalar is used as an argument. Standardize time zones and date/time formats in the API contract; do not rely on implicit formatting per client.

## 5. Configuration Areas Accessible via the Builder

In Spring for GraphQL 1.2/1.3 and Spring Boot 3.x, the customizer receives `GraphQlSource.SchemaResourceBuilder`. This builder provides APIs specific to schema resources and inherits shared configuration APIs.

| API | Purpose |
| --- | --- |
| `schemaResources(...)` | Adds schema resources to parse and merge |
| `configureTypeDefinitions(...)` | Adds or modifies type definitions before building `GraphQLSchema` |
| `configureRuntimeWiring(...)` | Registers scalars, data fetchers, directive wiring, and type resolvers |
| `defaultTypeResolver(...)` | Configures the default type resolver for interfaces and unions |
| `inspectSchemaMappings(...)` | Checks unmapped fields, mismatched registrations, and mapping issues |
| `schemaFactory(...)` | Supplies custom creation of `GraphQLSchema` from the type definition registry and runtime wiring |
| `configureGraphQl(...)` | Configures `GraphQL.Builder` before building the GraphQL runtime |
| `instrumentation(...)` | Registers GraphQL Java instrumentation |
| `exceptionResolvers(...)` | Adds resolvers to handle data fetcher exceptions |
| `subscriptionExceptionResolvers(...)` | Adds resolvers to handle subscription publisher errors |
| `typeVisitors(...)` | Traverses the schema to adjust `GraphQLCodeRegistry` |
| `typeVisitorsToTransformSchema(...)` | Uses visitors capable of transforming the schema itself |

Not every application needs to use all these APIs. Pick the extension point closest to your requirement. For example, registering custom scalars should go through `configureRuntimeWiring`; changing execution IDs should use `configureGraphQl`; checking that all resolvers are mapped should use `inspectSchemaMappings`.

### 5.1. Enabling Schema Mapping Inspection

As a schema evolves, a field may be declared in SDL without a resolver, or a data fetcher may be registered under a misspelled field name. Schema inspection helps detect these situations at startup.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GraphQlInspectionConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(GraphQlInspectionConfiguration.class);

    @Bean
    GraphQlSourceBuilderCustomizer schemaInspectionCustomizer() {
        return builder -> builder.inspectSchemaMappings(
                report -> log.info("GraphQL schema mapping report: {}", report)
        );
    }
}
~~~

Schema inspection was introduced in Spring for GraphQL 1.2. The report helps find unmapped fields, data fetcher registrations missing from the schema, mismatched arguments, and certain nullability discrepancies detectable from Java signatures. It is a mapping diagnostic tool, not a replacement for business logic or authorization testing.

### 5.2. Configuring the GraphQL Java Runtime

`configureGraphQl(...)` grants access to `graphql.GraphQL.Builder`. For instance, you can configure an execution ID provider so each execution gets an identifier following your system's convention:

~~~java
@Bean
GraphQlSourceBuilderCustomizer executionIdCustomizer(
        CustomExecutionIdProvider executionIdProvider
) {
    return builder -> builder.configureGraphQl(graphQlBuilder ->
            graphQlBuilder.executionIdProvider(executionIdProvider)
    );
}
~~~

`CustomExecutionIdProvider` in this example is an application-provided implementation of the `graphql.execution.ExecutionIdProvider` interface. Having a custom execution ID helps correlate logs, traces, and metrics for the same GraphQL operation. Never embed personal data or secrets in an execution ID.

### 5.3. Distinguishing Type Visitors and Schema Transformation

`typeVisitors(...)` uses `SchemaTraverser` to traverse schema elements and adjust `GraphQLCodeRegistry`; visitors used this way do not alter the schema structure.

`typeVisitorsToTransformSchema(...)` uses a transformation mechanism, allowing changes to `GraphQLSchema` itself. Transformation is more expensive, so use it only when you genuinely need to modify the schema structure. If your goal is only to attach or adjust data fetchers, consider runtime wiring or regular type visitors first.

## 6. GraphQlSourceBuilderCustomizer vs. RuntimeWiringConfigurer

These two extension points are related but have different scopes. Both are discovered by Spring Boot during GraphQL configuration, yet they serve two different levels of customization.

| Criterion | `RuntimeWiringConfigurer` | `GraphQlSourceBuilderCustomizer` |
| --- | --- | --- |
| Scope | Configures `RuntimeWiring.Builder` | Configures `GraphQlSource.SchemaResourceBuilder` and inherited builder APIs |
| Used for | Scalars, directives, type resolvers, data fetchers | Runtime wiring plus broader customizations such as schema factory, schema inspection, instrumentation, GraphQL builder, type visitors |
| Focus level | Narrow, targeted to runtime wiring | Broad, spanning `GraphQlSource` creation |
| When to choose | Only need to add wiring | Need to adjust `GraphQlSource` construction or multiple runtime aspects |

For example, if you only need to register a scalar, you can use `RuntimeWiringConfigurer`:

~~~java
@Bean
RuntimeWiringConfigurer dateTimeRuntimeWiringConfigurer() {
    return runtimeWiring -> runtimeWiring.scalar(ExtendedScalars.DateTime);
}
~~~

If you need to combine scalars with schema inspection or GraphQL runtime configuration in one callback, you can use `GraphQlSourceBuilderCustomizer`. Avoid creating a customizer solely to wrap a `RuntimeWiringConfigurer` when no broader builder configuration is needed.

## 7. Execution Order and Multiple Customizers

An application can declare multiple `GraphQlSourceBuilderCustomizer` beans. Spring Boot collects these beans according to Spring's ordering and applies each customizer to the builder before finalizing `GraphQlSource`.

When one customization depends on another, declare ordering explicitly using `@Order` or by implementing `Ordered`:

~~~java
import org.springframework.core.annotation.Order;

@Bean
@Order(10)
GraphQlSourceBuilderCustomizer scalarCustomizer() {
    return builder -> builder.configureRuntimeWiring(runtimeWiring ->
            runtimeWiring.scalar(ExtendedScalars.DateTime)
    );
}

@Bean
@Order(20)
GraphQlSourceBuilderCustomizer inspectionCustomizer() {
    return builder -> builder.inspectSchemaMappings(report ->
            log.info("GraphQL schema mapping report: {}", report)
    );
}
~~~

Customizers should generally be designed independently so they do not rely on ordering unnecessarily. `@Order` expresses ordering when dependencies exist, but it should not be used to mask multiple customizers overwriting the same setting.

Do not modify the builder from another thread or retain a reference to mutate it after the callback finishes. This is a startup-time builder; complete all changes synchronously inside `customize(...)` so Spring Boot can build the source consistently.

## 8. When to Use Properties, Beans, or a Customizer

Not every change needs `GraphQlSourceBuilderCustomizer`. Spring Boot already provides dedicated properties and bean extension points:

| Requirement | Configuration Approach to Consider First |
| --- | --- |
| Change schema locations | `spring.graphql.schema.locations` |
| Change schema file extensions | `spring.graphql.schema.file-extensions` |
| Register custom scalars or directives | `RuntimeWiringConfigurer` |
| Handle data fetcher exceptions | `DataFetcherExceptionResolver` bean |
| Handle subscription publisher errors | `SubscriptionExceptionResolver` bean |
| Add GraphQL Java instrumentation | `Instrumentation` bean or customizer if combined setup is needed |
| Customize GraphQL builder or schema factory | `GraphQlSourceBuilderCustomizer` |
| Completely replace the GraphQL source | Declare a `GraphQlSource` bean yourself and manage full setup |

By default, the Boot starter looks for `.graphqls` and `.gqls` schemas under `classpath:graphql/**`, which typically maps to `src/main/resources/graphql`. If you only need to change locations, using properties is easier to read and manage per environment than writing a customizer.

## 9. Interaction with Spring Boot Auto-configuration

`GraphQlSourceBuilderCustomizer` is consumed by the auto-configuration that builds `GraphQlSource`. In the default configuration, Spring Boot creates the builder, loads schema resources, applies properties, discovers wiring and instrumentation beans, and then invokes customizers.

The default `GraphQlSource` bean is conditional on no bean of that type already existing. If the application defines its own `GraphQlSource` bean, auto-configuration can back off and skip creating the default source. In that case, customizers meant for the auto-configuration builder are no longer applied to the application's manually created source. Move any necessary configuration into where your application constructs `GraphQlSource`.

This is especially important when migrating from auto-configuration to manual configuration. If a registered customizer appears to have no effect, check:

1. Is the application using the appropriate `spring-boot-starter-graphql`?
2. Were schemas discovered so GraphQL auto-configuration is activated?
3. Is a custom `GraphQlSource` bean causing default auto-configuration to back off?
4. Is the customizer within component scanning or imported into the application context?
5. Are SDL parsing or schema validation errors causing source creation to fail before the app becomes ready?
6. Is the customizer running in the right order, or is another customizer overriding the configuration?

## 10. Package Differences Between Spring Boot 3 and Spring Boot 4

When upgrading Spring Boot, note that the package of `GraphQlSourceBuilderCustomizer` changed in Spring Boot 4. The callback API still accepts `GraphQlSource.SchemaResourceBuilder`, but the import differs:

| Version | Package |
| --- | --- |
| Spring Boot 3.x | `org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer` |
| Spring Boot 4.x | `org.springframework.boot.graphql.autoconfigure.GraphQlSourceBuilderCustomizer` |

The examples above use the Spring Boot 3.x package. For Spring Boot 4.x, update the import to the new package. Do not copy a Boot 3 package into a Boot 4 project or vice versa. Also check the bundled Spring for GraphQL version to confirm that builder methods such as `inspectSchemaMappings` or `typeVisitorsToTransformSchema` exist in your actual dependency.

## 11. Testing Customizers

Customizers run during application context initialization, so verify that their configuration actually takes effect in the `GraphQlSource` produced by Spring Boot.

Example checking that a custom scalar is registered:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.execution.GraphQlSource;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class GraphQlSourceCustomizerTests {

    @Autowired
    GraphQlSource graphQlSource;

    @Test
    void registersDateTimeScalar() {
        assertThat(graphQlSource.schema().getType("DateTime"))
                .isNotNull();
    }
}
~~~

The test requires a schema declaring `scalar DateTime` and the Extended Scalars dependency in the test application context. Checking the schema only verifies that the type is registered. To verify parsing and serialization, execute a GraphQL operation with an argument or field returning `DateTime` using `GraphQlTester`.

Cases worth testing:

1. The customizer is discovered by Spring and invoked during context initialization.
2. Custom scalars, directives, or type resolvers are properly registered in the runtime schema.
3. Schema inspection detects invalid mappings as expected.
4. Customizers follow explicit ordering when configurations depend on one another.
5. When a custom `GraphQlSource` bean is defined, the application still configures the source as intended.
6. Invalid schemas or incompatible scalars cause context startup to fail with a diagnosable message.

There is no need to unit-test a lambda that merely calls one builder method if an integration test already verifies the resulting configuration behavior. Focus on testing the runtime outcome that clients and resolvers actually rely on.

## 12. Common Issues and How to Resolve Them

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `GraphQlSourceBuilderCustomizer` not found | Wrong package imported for Spring Boot version or missing starter | Check dependencies and Boot 3/4 package |
| SDL reports undeclared scalar or missing wiring | `scalar DateTime` is present without registering a scalar implementation | Register the scalar via `RuntimeWiringConfigurer` or customizer and check dependencies |
| Customizer has no effect | Application defines its own `GraphQlSource` bean | Apply settings in your custom source builder or remove the custom bean to use auto-configuration |
| Schema inspection reports unmapped field | SDL declares a field without a matching controller/data fetcher | Add a resolver or update the schema to match the contract |
| Schema fails on startup after adding customizer | Runtime wiring is incompatible with SDL or two settings conflict | Check schema, scalars, type resolvers, and customizer order |
| Builder API does not exist | Spring for GraphQL version is older than the version introducing that API | Check the dependency tree and Javadoc for the exact version |

When diagnosing, read the root error from `GraphQlSource` creation. Many schema and runtime wiring errors are caught right at application context startup, before the endpoint receives any request.

## 13. Workflow for Applying GraphQlSourceBuilderCustomizer

When you need to customize the GraphQL runtime in a Spring Boot application, follow these steps:

1. Determine whether the requirement can be met using Spring GraphQL properties or a specialized extension bean.
2. If broader customization of source creation is needed, declare a `GraphQlSourceBuilderCustomizer` bean.
3. Use the correct package for your Spring Boot version; verify the builder method exists in the managed Spring for GraphQL version.
4. Apply changes inside the callback without calling `build()` or retaining the builder for later mutation.
5. If multiple customizers depend on order, declare `@Order` and test the combined configuration.
6. Start the application context and inspect `GraphQlSource` or execute operations to verify the result.

`GraphQlSourceBuilderCustomizer` is an extension point for cases requiring deeper control over GraphQL runtime creation. Using it within its proper scope lets the application benefit from Spring Boot auto-configuration, keep configuration centralized, and avoid rebuilding infrastructure already provided by the starter.

## References

- [Spring Boot 3.5 — GraphQlSourceBuilderCustomizer API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/graphql/GraphQlSourceBuilderCustomizer.html)
- [Spring Boot 4.x — GraphQlSourceBuilderCustomizer API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/graphql/autoconfigure/GraphQlSourceBuilderCustomizer.html)
- [Spring for GraphQL — Request Execution and GraphQlSource](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Boot — Spring for GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [GraphQlSource.SchemaResourceBuilder API](https://docs.spring.io/spring-graphql/docs/1.2.x/api/org/springframework/graphql/execution/GraphQlSource.SchemaResourceBuilder.html)
