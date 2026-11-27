# SchemaResourceBuilder in Spring for GraphQL

`SchemaResourceBuilder` is the Spring for GraphQL builder used to create a `GraphQlSource` from one or more schema resources. It accepts Spring `Resource` objects, reads the SDL content, combines the definitions into a single GraphQL schema, and allows configuring runtime wiring before building.

This builder is useful when an application needs to explicitly control the list of schema files, load schemas from the classpath or filesystem, or create a `GraphQlSource` outside of Spring Boot auto-configuration. If you only need to change the schema directory in a typical Spring Boot application, starter properties are usually sufficient; understanding the builder helps you choose the right configuration level and avoid accidentally omitting runtime components that Boot normally sets up.

## 1. GraphQlSource and SchemaResourceBuilder

Spring for GraphQL uses `GraphQlSource` to provide the GraphQL schema and the runtime built from that schema. `GraphQlSource` serves as the input for `ExecutionGraphQlService`, the component that executes operations and coordinates data fetchers.

`GraphQlSource` provides the factory method:

~~~java
GraphQlSource.schemaResourceBuilder()
~~~

This method returns `GraphQlSource.SchemaResourceBuilder`. The builder accepts schema resources and inherits the common configuration capabilities of `GraphQlSource.Builder`.

A typical schema creation flow:

~~~mermaid
flowchart TD
    A[Spring Resource objects] --> B[SchemaResourceBuilder]
    B --> C[Read SDL resources]
    C --> D[Parse type definitions]
    D --> E[Merge schema definitions and extensions]
    E --> F[Build GraphQLSchema]
    G[RuntimeWiringConfigurer] --> H[RuntimeWiring]
    F --> I[GraphQL runtime]
    H --> I
    I --> J[GraphQlSource]
    J --> K[ExecutionGraphQlService]
~~~

The steps above describe the high-level role. The builder combines schema definitions with runtime wiring to create a complete GraphQL runtime. SDL describes types and fields; runtime wiring provides how fields, scalars, type resolvers, and related components are executed.

## 2. Creating GraphQlSource from a single resource

If the schema consists of only one file, you can create the builder and pass a `ClassPathResource`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.graphql.execution.GraphQlSource;

@Configuration(proxyBeanMethods = false)
public class GraphQlSourceConfiguration {

    @Bean
    GraphQlSource graphQlSource() {
        return GraphQlSource.schemaResourceBuilder()
                .schemaResources(
                        new ClassPathResource("graphql/schema.graphqls")
                )
                .build();
    }
}
~~~

`schemaResources(...)` accepts Spring `Resource` objects. `ClassPathResource` points to a file on the classpath, typically located in `src/main/resources`. The path passed to `ClassPathResource` is relative to the classpath, not an absolute path on the development machine.

Example `src/main/resources/graphql/schema.graphqls` file:

~~~graphql
type Query {
    apiVersion: String!
    greeting(name: String!): String!
}
~~~

When the application starts, the builder reads the file, parses the SDL, and creates the schema. If the resource does not exist or the SDL is invalid, creating the `GraphQlSource` fails; the application should catch this error at startup rather than waiting for a client to send a request.

## 3. Loading multiple schema resources

In larger applications, the schema is often split by domain. `SchemaResourceBuilder` lets you pass multiple resources in a single call:

~~~java
@Bean
GraphQlSource graphQlSource() {
    return GraphQlSource.schemaResourceBuilder()
            .schemaResources(
                    new ClassPathResource("graphql/schema.graphqls"),
                    new ClassPathResource("graphql/book/book.graphqls"),
                    new ClassPathResource("graphql/author/author.graphqls"),
                    new ClassPathResource("graphql/member/member.graphqls")
            )
            .build();
}
~~~

Example files:

`graphql/schema.graphqls` declares the root type:

~~~graphql
type Query {
    apiVersion: String!
}
~~~

`graphql/book/book.graphqls` declares types and extends the query:

~~~graphql
type Book {
    id: ID!
    title: String!
}

extend type Query {
    book(id: ID!): Book
    books: [Book!]!
}
~~~

`graphql/author/author.graphqls` declares the author domain:

~~~graphql
type Author {
    id: ID!
    name: String!
}

extend type Query {
    author(id: ID!): Author
    authors: [Author!]!
}
~~~

After building, these definitions form a single `GraphQLSchema`. Clients still send queries to a single GraphQL endpoint and can select fields from multiple domains in the same operation.

## 4. Spring Resource and choosing a schema source

`SchemaResourceBuilder` works with the `org.springframework.core.io.Resource` abstraction, so the schema source is not limited to the classpath.

| Resource | Data source | Use case |
| --- | --- | --- |
| `ClassPathResource` | Resource packaged on the classpath | Schema located in `src/main/resources` or inside a dependency JAR |
| `FileSystemResource` | File on the filesystem | Schema mounted or placed outside the application artifact |
| `UrlResource` | Resource with a URL | Schema served via a URL accessible to the application |
| `ByteArrayResource` | In-memory byte array | Testing or cases where the schema is generated at runtime |

Example using a file outside the classpath:

~~~java
import org.springframework.core.io.FileSystemResource;

GraphQlSource source = GraphQlSource.schemaResourceBuilder()
        .schemaResources(
                new FileSystemResource("/opt/app/graphql/schema.graphqls")
        )
        .build();
~~~

Filesystem paths depend on the deployment environment. If the schema needs to travel with the application and run reliably inside a JAR, place it on the classpath. If the schema is managed outside the artifact, ensure the file exists, has read permissions, and has a schema version compatible with the application version.

## 5. Using ResourcePatternResolver to load by pattern

`SchemaResourceBuilder.schemaResources(...)` accepts concrete `Resource` instances; it is not an API that automatically scans directories using wildcards. When you want to retrieve all SDL files in subdirectories, use `ResourcePatternResolver` to locate the resources first, then pass the resulting array to the builder.

~~~java
import java.io.IOException;

import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.core.io.support.ResourcePatternResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.GraphQlSource;

@Configuration(proxyBeanMethods = false)
public class GraphQlResourcePatternConfiguration {

    @Bean
    GraphQlSource graphQlSource() throws IOException {
        ResourcePatternResolver resolver =
                new PathMatchingResourcePatternResolver();

        Resource[] resources = resolver.getResources(
                "classpath*:graphql/**/*.graphqls"
        );

        if (resources.length == 0) {
            throw new IllegalStateException(
                    "No GraphQL schema resources found"
            );
        }

        return GraphQlSource.schemaResourceBuilder()
                .schemaResources(resources)
                .build();
    }
}
~~~

The pattern `classpath*:graphql/**/*.graphqls` finds `.graphqls` files in the `graphql` directory and its subdirectories across the entire classpath. The `classpath*:` prefix is useful when resources may reside across multiple classpath roots or dependency JARs. If the application also uses `.gqls`, search for that extension as well and merge the results before passing them to the builder.

Avoid scanning too broadly such as `classpath*:**/*.graphqls`, because you might accidentally load schemas from libraries or modules that do not belong to the current API. Scope the pattern to a clear namespace, such as `graphql/**`.

## 6. Distinguishing resource patterns from Spring Boot schema locations

When using `spring-boot-starter-graphql`, Spring Boot auto-configures `GraphQlSource` and searches for schemas based on `spring.graphql.schema.locations`. By default, schemas are typically searched in `classpath:graphql/**/` with `.graphqls` and `.gqls` extensions.

Configuration example:

~~~yaml
spring:
  graphql:
    schema:
      locations: classpath:graphql/**/
      file-extensions: .graphqls,.gqls
~~~

If schemas are located in another directory:

~~~yaml
spring:
  graphql:
    schema:
      locations:
        - classpath:graphql/**/
        - classpath:shared-graphql/**/
~~~

These two configuration approaches serve different purposes:

| Approach | Role |
| --- | --- |
| `spring.graphql.schema.locations` | Declares locations/patterns for Spring Boot auto-configuration to locate schema resources |
| `ResourcePatternResolver` | Manually finds `Resource` instances by pattern in Java code |
| `SchemaResourceBuilder.schemaResources(...)` | Accepts resolved `Resource` instances and builds `GraphQlSource` |

If you only need to add a schema directory for a Boot application, use properties first. Creating a custom `GraphQlSource` bean is only necessary when you want direct control over building the source or are building an application without auto-configuration.

## 7. SchemaResourceBuilder and RuntimeWiring

Schema resources contain only SDL definitions. For GraphQL to execute fields, the runtime needs the corresponding `RuntimeWiring`. Spring for GraphQL provides `RuntimeWiringConfigurer` to register scalars, data fetchers, directive wiring, and type resolvers.

Example configuring the `DateTime` scalar while building the source:

~~~java
import graphql.scalars.ExtendedScalars;
import org.springframework.graphql.execution.GraphQlSource;

GraphQlSource source = GraphQlSource.schemaResourceBuilder()
        .schemaResources(
                new ClassPathResource("graphql/schema.graphqls")
        )
        .configureRuntimeWiring(wiring ->
                wiring.scalar(ExtendedScalars.DateTime)
        )
        .build();
~~~

In a Spring Boot application, `RuntimeWiringConfigurer` beans are usually collected and applied by auto-configuration. When manually creating `GraphQlSource`, you must actively pass the required configurers into the builder. The example below applies the configurers in Spring order:

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.graphql.execution.GraphQlSource;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Bean
GraphQlSource graphQlSource(
        ObjectProvider<RuntimeWiringConfigurer> configurers
) {
    GraphQlSource.SchemaResourceBuilder builder =
            GraphQlSource.schemaResourceBuilder()
                    .schemaResources(
                            new ClassPathResource("graphql/schema.graphqls"),
                            new ClassPathResource("graphql/book/book.graphqls")
                    );

    configurers.orderedStream()
            .forEach(builder::configureRuntimeWiring);

    return builder.build();
}
~~~

This snippet illustrates how to apply existing configurer beans, including those that register controllers if they are already configured in the application context. When replacing the default GraphQlSource yourself, explicitly verify which runtime wiring beans need to be passed to the builder; if `AnnotatedControllerConfigurer` is omitted, `@QueryMapping`, `@MutationMapping`, or `@SchemaMapping` methods may not be registered as data fetchers.

## 8. Other builder configurations

`SchemaResourceBuilder` inherits configuration points from `GraphQlSource.Builder`. Beyond `schemaResources(...)`, commonly used APIs include:

| API | Purpose |
| --- | --- |
| `configureRuntimeWiring(...)` | Applies one or more `RuntimeWiringConfigurer` instances |
| `defaultTypeResolver(...)` | Provides a default type resolver for interfaces and unions |
| `schemaFactory(...)` | Customizes how `GraphQLSchema` is built from the type definition registry and runtime wiring |
| `configureGraphQl(...)` | Customizes `GraphQL.Builder` before creating the runtime |
| `instrumentation(...)` | Registers GraphQL Java instrumentation |
| `exceptionResolvers(...)` | Configures resolvers to handle data fetcher exceptions |
| `subscriptionExceptionResolvers(...)` | Configures error handling for subscription publishers |
| `inspectSchemaMappings(...)` | Inspects schema mappings and reports mismatches |

You do not need to configure every API for every application. Choose extension points as needed: scalars and type resolvers belong to runtime wiring; schema factory is only needed when altering schema creation; instrumentation is used for observability or execution customization; schema inspection helps catch mapping errors at startup.

## 9. Organizing SDL for accurate builder merging

When loading multiple resources, GraphQL still validates the result as a single schema. Splitting files does not create separate namespaces per domain.

A commonly used structure:

~~~text
src/main/resources/
└── graphql/
    ├── schema.graphqls
    ├── common/
    │   ├── scalars.graphqls
    │   └── enums.graphqls
    ├── book/
    │   ├── book.graphqls
    │   └── book-mutation.graphqls
    └── author/
        └── author.graphqls
~~~

Rules to follow:

1. Each object type, input type, enum, scalar, and directive has only one base definition.
2. Use `extend type Query` or `extend type Mutation` for domains to add fields to a previously declared root type.
3. A type extension must have a corresponding base type in the merged schema.
4. Do not duplicate field names within the same object type.
5. Custom scalars declared in SDL must have an implementation in runtime wiring.
6. Do not rely on filename ordering to resolve dependencies between types; the merged schema must be valid after all resources are loaded.

Example base file declaring the root type:

~~~graphql
type Query {
    apiVersion: String!
}
~~~

Book domain file extending the root type:

~~~graphql
type Book {
    id: ID!
    title: String!
}

extend type Query {
    books: [Book!]!
}
~~~

If `book.graphqls` has `extend type Query` but no resource declares `type Query`, parsing/validation will fail. Therefore, validate the entire set of discovered resources, not just each file individually.

## 10. Does creating a custom GraphQlSource replace auto-configuration?

In Spring Boot, the default `GraphQlSource` is created conditionally when no bean of the same type exists. When an application declares its own `GraphQlSource` bean, the auto-configuration that creates the default source backs off.

This means the application takes responsibility for creating the schema and configuring runtime wiring for that source. Settings previously applied by Boot via properties or extension beans must be re-examined, especially:

- `RuntimeWiringConfigurer` beans, including the controller configurer.
- Custom scalars and type resolvers.
- Instrumentation and exception resolvers.
- Schema inspection or custom schema factory.
- Resource locations and file extensions.

If the goal is merely to add a scalar or enable schema inspection, it is usually better to keep auto-configuration and use a `RuntimeWiringConfigurer` or `GraphQlSourceBuilderCustomizer` bean. Creating a custom `GraphQlSource` is a broader change because the application directly controls the build step.

## 11. Testing SchemaResourceBuilder

You can directly test the schema built from resources. Example with JUnit and AssertJ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.graphql.execution.GraphQlSource;

import static org.assertj.core.api.Assertions.assertThat;

class GraphQlSourceBuilderTests {

    @Test
    void buildsSchemaFromMultipleResources() {
        GraphQlSource source = GraphQlSource.schemaResourceBuilder()
                .schemaResources(
                        new ClassPathResource("graphql/schema.graphqls"),
                        new ClassPathResource("graphql/book/book.graphqls"),
                        new ClassPathResource("graphql/author/author.graphqls")
                )
                .build();

        assertThat(source.schema().getType("Query")).isNotNull();
        assertThat(source.schema().getType("Book")).isNotNull();
        assertThat(source.schema().getType("Author")).isNotNull();
    }
}
~~~

These schema files must be in `src/test/resources` or `src/main/resources` on the test runtime. This test verifies that the builder read and merged the types. If you need to verify that resolvers work, add an integration test with `ExecutionGraphQlService` or a Spring for GraphQL test slice to execute an operation.

With a Spring Boot application, `@GraphQlTest` can test the schema and controllers in a test slice:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;

import static org.assertj.core.api.Assertions.assertThat;

@GraphQlTest(BookController.class)
class BookSchemaTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void exposesBookFieldFromDomainSchema() {
        graphQlTester.document("""
                query {
                    books {
                        id
                        title
                    }
                }
                """)
            .execute()
            .errors()
            .satisfy(errors -> assertThat(errors).isEmpty());
    }
}
~~~

This test assumes `BookController` and its dependencies are present in the test slice or appropriately mocked. If you only want to test schema parsing, the direct builder test above has fewer dependencies.

## 12. Common errors when loading schema resources

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Schema resource not found | Incorrect classpath path or resource not packaged | Check `src/main/resources` location and filename |
| Builder receives an empty resource array | Pattern does not match or wrong prefix used | Check `classpath:`/`classpath*:` and file extensions |
| `Type ... not found` | Missing resource defining the referenced type | Add the resource or fix the type name |
| `Cannot extend type ... because it is not defined` | Type extension present without base type | Declare the base root/object type in a loaded resource |
| Duplicate type or field | Multiple files define the same name | Keep only one base definition and use valid type extensions |
| Schema builds successfully but resolvers do not run | Runtime wiring has not registered data fetchers/controller configurer | Pass the required `RuntimeWiringConfigurer` beans to the builder |
| Custom scalar fails to parse | SDL declares scalar but runtime wiring lacks implementation | Add scalar implementation to runtime wiring |
| Works in IDE but fails in JAR | Machine-dependent filesystem path or unpackaged resource | Use classpath resources or explicit external resource configuration |
| Custom GraphQlSource loses Boot configuration | Auto-configuration backed off due to custom source bean | Reapply needed properties and runtime wiring in the builder |

When diagnosing, check the count and names of discovered resources first, then check SDL errors, and finally runtime wiring. These three stages help distinguish file discovery errors, schema errors, and execution errors.

## 13. Process for choosing a schema loading approach

When building a GraphQL API with Spring for GraphQL, you can choose a schema loading approach based on your needs:

1. For a standard Spring Boot application, place SDL in `src/main/resources/graphql` and use auto-configuration.
2. When you only need to change or add schema directories, configure `spring.graphql.schema.locations`.
3. When you need to manually discover resources using wildcards, use `ResourcePatternResolver` to get `Resource[]` and pass them to `schemaResources(...)`.
4. When you need to specify a few exact files, use `ClassPathResource`, `FileSystemResource`, or an appropriate `Resource` type.
5. When manually building `GraphQlSource`, apply the required `RuntimeWiringConfigurer` beans and verify controllers, scalars, type resolvers, and exception resolvers.
6. Test both the merged schema and actual operations; also verify how resources are packaged in the JAR.

`SchemaResourceBuilder` is the direct entry point for turning Spring `Resource` objects containing SDL into a `GraphQlSource`. By clearly separating resource discovery, schema merging, and runtime wiring configuration, an application can organize schemas by domain or deployment environment while maintaining a unified GraphQL schema.

## References

- [Spring for GraphQL — GraphQlSource API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/GraphQlSource.html)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Boot — Spring for GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Spring Framework — Resource abstraction](https://docs.spring.io/spring-framework/reference/core/resources.html)
- [Spring Framework — Resource pattern resolution](https://docs.spring.io/spring-framework/reference/core/resources.html#resources-resourceloader)
