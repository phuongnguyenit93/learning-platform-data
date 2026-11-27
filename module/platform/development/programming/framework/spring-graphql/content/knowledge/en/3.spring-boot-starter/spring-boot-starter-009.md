# Spring Boot Auto-configuration in Spring for GraphQL

## Objectives

After this lesson, you will be able to:

- Explain what Spring Boot auto-configuration handles and how it works.
- Understand the roles of starters, classpath, conditional annotations, beans, and application properties.
- Describe how Spring Boot auto-configures the foundational components of Spring for GraphQL.
- Know how SDL schemas are discovered, loaded, and assembled into the GraphQL runtime.
- Configure GraphQL endpoints, transports, and related features using application.properties or application.yml.
- Add resolvers, runtime wiring, scalars, instrumentation, and customizers while still leveraging auto-configuration.
- Recognize when auto-configuration backs off to defer to application-provided beans.
- Diagnose cases where auto-configuration is not activated or is unintentionally disabled.

## 1. What Is Auto-configuration?

Auto-configuration is the mechanism by which Spring Boot automatically registers beans and sets up application infrastructure based on what is on the classpath, which beans already exist, and the application's configuration.

When you add a starter to a project, the starter brings the necessary libraries onto the classpath. Spring Boot detects those libraries and evaluates the corresponding auto-configurations. When conditions match, Boot registers foundational beans so the application can run with minimal manual configuration.

With Spring for GraphQL, auto-configuration gives the application ready-to-use components such as:

- A GraphQL runtime built from SDL schemas and runtime wiring.
- Mechanisms connecting controller methods to fields in the schema.
- The GraphQL service and web handlers to serve requests.
- Transports suited to the active web stack, such as Spring MVC or WebFlux.
- Supporting components such as the DataLoader registry and observability when the corresponding dependencies and configuration are present.

Auto-configuration does not design your business schema, write field resolvers, or decide data access permissions. The application still must provide schemas, controllers, business services, and appropriate policies.

You can think of auto-configuration as infrastructure assembly. It wires foundational components according to common conventions so the development team can focus on the API and business logic.

## 2. How Do Starters, Dependencies, and Auto-configuration Relate?

In a Spring Boot project, a starter is typically an aggregate dependency. It pulls in the libraries required for a set of capabilities.

For example, a project using Spring for GraphQL typically declares the starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-graphql</artifactId>
</dependency>
~~~

If using Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
}
~~~

Let Spring Boot manage dependency versions through its parent/BOM or equivalent dependency management mechanism, avoiding manual pinning of Spring GraphQL and GraphQL Java versions incompatible with the Boot version in use.

Adding a starter only places libraries onto the classpath. Auto-configurations are only applied when the application starts through Spring Boot's startup mechanism and their conditions are satisfied.

Several related starters may be added depending on the stack and requirements, such as the MVC web starter, WebFlux, or RSocket. Which transport gets activated depends on dependencies and application conditions, so do not assume that adding the GraphQL starter alone enables every transport.

High-level flow:

~~~mermaid
flowchart TD
    A["Declare spring-boot-starter-graphql"] --> B["Libraries appear on the classpath"]
    B --> C["Spring Boot discovers auto-configurations"]
    C --> D{"Are the conditions satisfied?"}
    D -->|Yes| E["Register foundational beans"]
    D -->|No| F["Skip that configuration"]
    E --> G["Application adds schema and resolvers"]
    F --> G
    G --> H["GraphQL API ready with final configuration"]
~~~

## 3. How Spring Boot Decides Whether to Apply Auto-configuration

Auto-configuration does not run unconditionally. Spring Boot uses conditions to decide whether a configuration or bean should be created.

### 3.1. Classpath Conditions

**@ConditionalOnClass** checks whether one or more classes exist on the classpath.

Conceptual example:

~~~java
@AutoConfiguration
@ConditionalOnClass(GraphQlSource.class)
class GraphQlInfrastructureAutoConfiguration {
    // Declare foundational GraphQL beans
}
~~~

If the application lacks the library providing **GraphQlSource**, this configuration is not applied. Classpath conditions allow a library to offer optional features without forcing every application to install all related dependencies.

### 3.2. Bean Conditions

**@ConditionalOnMissingBean** creates a default bean only when no matching bean has already been registered by the application or another configuration.

~~~java
@Bean
@ConditionalOnMissingBean
GraphQlMetrics graphQlMetrics() {
    return new DefaultGraphQlMetrics();
}
~~~

The example above merely illustrates the mechanism. If the application registers its own **GraphQlMetrics** bean, the default bean can back off and the application's bean is used instead.

**@ConditionalOnBean** does the opposite: it applies a configuration only when a dependent bean already exists.

This mechanism lets an application replace parts of the infrastructure selectively. However, providing your own foundational bean may cause Boot to skip a default bean that handled broader responsibilities. Make sure you understand a bean's full responsibilities before replacing it.

### 3.3. Property Conditions

**@ConditionalOnProperty** checks configuration values. For example, a feature may only be enabled when a property is set to **true**.

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "app.graphql.audit",
        name = "enabled",
        havingValue = "true")
GraphQlAuditListener graphQlAuditListener() {
    return new GraphQlAuditListener();
}
~~~

This example demonstrates application-specific configuration. For standard Spring Boot properties, use the exact property names published by the Boot version in use.

### 3.4. Application Environment Conditions

Boot also has conditions to distinguish servlet web applications, reactive web applications, non-web applications, or test environments.

For example, Spring MVC configuration should only apply when required MVC classes are on the classpath and the application runs as the matching web application type. WebFlux configuration has corresponding conditions.

Thanks to this, the same Spring GraphQL application can select the transport matching its web stack without initializing both stacks.

### 3.5. Ordered Auto-configuration

Auto-configurations can declare before/after ordering relationships so dependent beans are evaluated at the right time. Annotations such as **@AutoConfigureBefore**, **@AutoConfigureAfter**, or the **before**/**after** attributes on **@AutoConfiguration** serve this purpose.

Ordering should not be used as a cure-all for bean problems. If two configurations both create a bean without clear conditions, review their conditions and responsibility boundaries.

## 4. How Spring Boot Discovers Auto-configuration

In modern Spring Boot versions, auto-configuration libraries publish their configuration list via the file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

This file lists classes annotated with **@AutoConfiguration**. Spring Boot reads the list and evaluates each configuration's conditions during application context initialization.

In older Boot versions, auto-configuration registration used metadata in **META-INF/spring.factories**. When upgrading Boot versions or authoring a custom starter library, follow the discovery mechanism of the target version.

In an application using **@SpringBootApplication**, this annotation includes component scanning and enables auto-configuration through **@EnableAutoConfiguration**.

~~~java
@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

There is no need to add **@EnableAutoConfiguration** again when **@SpringBootApplication** is already used.

Also distinguish:

- **Component scanning** locates components declared by the application, such as **@Controller**, **@Service**, and **@Component**.
- **Auto-configuration discovery** locates auto-configuration classes published by libraries.
- **Configuration properties binding** converts values from configuration files, environment variables, or other property sources into configuration objects.

These three mechanisms work together, each serving its own purpose.

## 5. Spring for GraphQL Auto-configuration

When GraphQL dependencies are present and the application boots via Spring Boot, GraphQL auto-configurations assemble the infrastructure based on the required conditions.

Conceptually, the process consists of:

1. Reading properties under the **spring.graphql** group.
2. Locating SDL schema files at the configured locations.
3. Building **GraphQlSource** from schemas and runtime wiring.
4. Registering the GraphQL components required to execute requests.
5. Wiring the web handler to the transport supported by the application.
6. Adding integration components when matching dependencies and conditions are present.

Internal class names, specific conditions, and configuration ordering may vary across Spring Boot versions. When you need to verify an exact bean in your project, inspect the condition report or the documentation for the exact version in use.

### 5.1. GraphQlSource and SDL Schemas

One of the most important tasks of auto-configuration is creating the GraphQL runtime from schemas.

By default convention, Spring Boot looks for schemas on the classpath under the directory:

~~~text
src/
└── main/
    └── resources/
        └── graphql/
            ├── schema.graphqls
            └── catalog.graphqls
~~~

Files with supported GraphQL schema extensions are loaded and combined into the application schema. Locations and extensions can be adjusted via properties.

Example schema:

~~~graphql
type Book {
    id: ID!
    title: String!
}

type Query {
    book(id: ID!): Book
}
~~~

Once the schema exists, the application must provide a DataFetcher for the **book** field. In Spring for GraphQL, a controller method can handle that:

~~~java
@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    Book book(@Argument String id) {
        return bookService.findById(id);
    }
}
~~~

Spring for GraphQL detects the controller and registers the corresponding mapping. Auto-configuration provides the GraphQL infrastructure; application controllers provide business behavior for fields.

### 5.2. RuntimeWiringConfigurer and Custom Scalars

When a schema needs additional scalars or wiring, the application can register a **RuntimeWiringConfigurer**.

~~~java
@Configuration
class GraphQlRuntimeConfiguration {

    @Bean
    RuntimeWiringConfigurer runtimeWiringConfigurer() {
        return wiringBuilder -> {
            // Register scalars, type resolvers, or additional wiring
        };
    }
}
~~~

This is the extension point for runtime wiring. Boot collects registered **RuntimeWiringConfigurer** beans and applies them when building the GraphQL runtime.

For example, a custom **DateTime** scalar needs an appropriate serializer and parser. Declaring **scalar DateTime** in SDL alone is not enough for the runtime to know how to convert between its GraphQL representation and Java types.

~~~graphql
scalar DateTime

type Event {
    id: ID!
    startsAt: DateTime!
}
~~~

When the application adds scalars, ensure the scalar name in wiring matches the name used in the schema.

### 5.3. GraphQlSourceBuilderCustomizer

In Spring Boot, **GraphQlSourceBuilderCustomizer** lets you customize building the GraphQL source at the builder level.

This extension point is useful when you need to tweak runtime build configuration without replacing the entire auto-configuration mechanism.

~~~java
@Bean
GraphQlSourceBuilderCustomizer graphQlSourceBuilderCustomizer() {
    return builder -> {
        // Customize the GraphQlSource builder according to the API of the version in use
    };
}
~~~

Exact customization details depend on the builder API of your Spring Boot/Spring GraphQL version. Do not copy a method from an example for another version without checking the current API.

### 5.4. Transports and Web Handlers

Once the GraphQL runtime and execution service exist, the application needs a transport so clients can send requests.

With Spring MVC, Boot can configure the GraphQL HTTP endpoint when MVC conditions match. With WebFlux, Boot can configure the corresponding reactive endpoint. WebSocket or RSocket integrations have their own conditions and properties.

The default HTTP endpoint is usually **/graphql**. You can change the path with:

~~~yaml
spring:
  graphql:
    path: /api/graphql
~~~

When changing the path, clients must send requests to the new path. If using a reverse proxy or API gateway, synchronize external routes with the internal application endpoint.

GraphiQL is a browser UI for exploring and testing GraphQL APIs. It is not required for the API to work and is typically disabled by default. Enable it only in appropriate environments and consider security policies during deployment.

## 6. Configuring with application.properties and application.yml

Spring Boot provides the **spring.graphql** property group to configure common settings.

YAML example:

~~~yaml
spring:
  graphql:
    path: /graphql
    schema:
      locations: classpath:graphql/
      file-extensions: .graphqls,.gqls
    graphiql:
      enabled: false
~~~

Equivalent example in **application.properties**:

~~~properties
spring.graphql.path=/graphql
spring.graphql.schema.locations=classpath:graphql/
spring.graphql.schema.file-extensions=.graphqls,.gqls
spring.graphql.graphiql.enabled=false
~~~

Meaning:

| Property | Purpose |
| --- | --- |
| **spring.graphql.path** | Path of the GraphQL HTTP endpoint |
| **spring.graphql.schema.locations** | Locations to search for SDL schemas |
| **spring.graphql.schema.file-extensions** | Schema file extensions to scan |
| **spring.graphql.graphiql.enabled** | Enables/disables the GraphiQL UI when supported by the integration |

Verify property names and default values against your project's Boot version. Setting a property unsupported by the current version in a config file may not produce the expected behavior.

### 6.1. Separating Configuration by Environment

Not every environment should enable the same features. Profiles can be used to separate configuration:

~~~yaml
# application-dev.yml
spring:
  graphql:
    graphiql:
      enabled: true
~~~

~~~yaml
# application-prod.yml
spring:
  graphql:
    graphiql:
      enabled: false
~~~

Activate a profile via environment variables or application run arguments:

~~~properties
spring.profiles.active=dev
~~~

Do not store secrets, tokens, or passwords in committed configuration files. Use environment variables, a secret manager, or your deployment platform's secure configuration mechanism.

## 7. Auto-configuration Backs Off When the Application Provides Beans

A core principle of Spring Boot is that default configuration can back off to allow application customization.

Suppose the application supplies its own **GraphQlSource** bean built from custom schemas and runtime wiring. The auto-configuration creating the default **GraphQlSource** typically includes a condition to create it only when no matching bean is present. When declaring the bean yourself, the **@Bean** method must return an actual **GraphQlSource** built using the API suited to your Spring GraphQL version.

When a custom bean is present, auto-configuration may refrain from creating the default bean. Configurations depending on that bean can continue working if the replacement bean satisfies the expected contract.

### 7.1. Property or Custom Bean?

Choose the smallest customization level that meets your requirement:

| Need | Configuration Approach to Consider |
| --- | --- |
| Change the GraphQL URL | **spring.graphql.path** property |
| Change where schemas live | **spring.graphql.schema.locations** |
| Enable/disable GraphiQL | Corresponding property |
| Add business DataFetchers | **@Controller**, **@QueryMapping**, **@SchemaMapping** |
| Register scalars or type resolvers | **RuntimeWiringConfigurer** |
| Customize the GraphQL source builder | **GraphQlSourceBuilderCustomizer** |
| Replace a foundational bean | Register the corresponding bean yourself when truly needed |

Declaring a foundational bean manually can cause Boot to back off from default configuration. Before replacing one, check that dependent beans are still created and wired properly.

### 7.2. Do Not Exclude Auto-configuration Prematurely

Spring Boot lets you exclude auto-configurations using the **exclude** attribute or corresponding exclusion property. However, excluding the entire GraphQL configuration can prevent many foundational beans from being registered.

Only use exclusions when you truly intend to manage that entire configuration area yourself or when a specific conflicting configuration has been clearly identified.

~~~java
@SpringBootApplication(exclude = SomeAutoConfiguration.class)
class CatalogApplication {
}
~~~

The class name in this example is an illustrative placeholder; use the exact auto-configuration class published by the library in use. In many cases, adding a bean or adjusting a property is sufficient and far less intrusive.

## 8. Writing Auto-configuration for an Internal Library

When building a library reused across multiple applications, you can create your own auto-configuration. For instance, a library might provide a shared set of GraphQL policies.

A basic auto-configuration:

~~~java
@AutoConfiguration
@ConditionalOnClass(GraphQlSource.class)
public class CompanyGraphQlAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    CompanyGraphQlPolicy companyGraphQlPolicy() {
        return new DefaultCompanyGraphQlPolicy();
    }
}
~~~

Meaning:

- **@AutoConfiguration** marks the class as a Boot auto-configuration.
- **@ConditionalOnClass** activates only when the required GraphQL API is on the classpath.
- **@ConditionalOnMissingBean** allows applications to override the default policy.

For Boot to discover the configuration, the library must declare the class in:

~~~text
src/main/resources/
└── META-INF/
    └── spring/
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

The file contents are the fully qualified class names, one configuration per line:

~~~text
com.example.graphql.CompanyGraphQlAutoConfiguration
~~~

A starter library typically separates the aggregate dependency module from the auto-configuration module so consumers can opt into features with a clean dependency. Specific module structure depends on library organization and project scale.

### 8.1. Using Configuration Properties for Libraries

Avoid scattering arbitrary configuration strings across multiple classes. Group configuration into a class annotated with **@ConfigurationProperties**.

~~~java
@ConfigurationProperties(prefix = "company.graphql")
public class CompanyGraphQlProperties {

    private boolean auditEnabled;

    public boolean isAuditEnabled() {
        return auditEnabled;
    }

    public void setAuditEnabled(boolean auditEnabled) {
        this.auditEnabled = auditEnabled;
    }
}
~~~

The auto-configuration can enable binding for this class:

~~~java
@AutoConfiguration
@EnableConfigurationProperties(CompanyGraphQlProperties.class)
public class CompanyGraphQlAutoConfiguration {
}
~~~

Applications using the library can configure it as:

~~~yaml
company:
  graphql:
    audit-enabled: true
~~~

In production code, consider constructor binding or records in a style matching your target Boot version, and generate configuration metadata so IDEs provide property suggestions.

### 8.2. Testing Auto-configuration

Do not test only that the application context starts successfully. Test both activation conditions and back-off behavior.

**ApplicationContextRunner** helps build a lightweight context with the target auto-configuration:

~~~java
class CompanyGraphQlAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            CompanyGraphQlAutoConfiguration.class));

    @Test
    void createsDefaultPolicyWhenMissing() {
        this.contextRunner.run(context -> {
            assertThat(context)
                    .hasSingleBean(CompanyGraphQlPolicy.class);
        });
    }

    @Test
    void backsOffWhenApplicationDefinesPolicy() {
        this.contextRunner
                .withBean(CompanyGraphQlPolicy.class,
                        () -> new CustomCompanyGraphQlPolicy())
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(CompanyGraphQlPolicy.class);
                    assertThat(context.getBean(CompanyGraphQlPolicy.class))
                            .isInstanceOf(CustomCompanyGraphQlPolicy.class);
                });
    }
}
~~~

The class names in the example are types defined by the illustrative library. In real tests, add classpath, property, and dependent bean conditions to accurately reflect your auto-configuration's contract.

## 9. Diagnosing Auto-configuration

When a GraphQL endpoint does not appear or an expected bean is not created, check systematically in order.

### 9.1. Verify Dependencies

Check whether starters and version management dependencies are correct. If required GraphQL classes are missing from the classpath, **@ConditionalOnClass** conditions will not match.

You can inspect the dependency tree with Maven:

~~~bash
./mvnw dependency:tree
~~~

Or Gradle:

~~~bash
./gradlew dependencies
~~~

Exact commands may differ depending on OS and project setup.

### 9.2. Enable the Condition Evaluation Report

Run the application with the **--debug** flag so Spring Boot prints the auto-configuration condition report:

~~~bash
java -jar app.jar --debug
~~~

The report helps distinguish:

- Which configurations were applied.
- Which configurations were skipped.
- Which conditions failed to match.
- Which existing beans caused defaults to back off.

If the application includes Spring Boot Actuator and the conditions endpoint is enabled, you can use the **conditions** endpoint to view the corresponding report. Management endpoints must be secured and exposed only according to operational policy.

### 9.3. Check Schema Locations

If the application starts but GraphQL schemas are not loaded as expected:

- Check that files reside in **src/main/resources/graphql/** or the configured location.
- Check that file extensions are supported.
- Check SDL syntax and referenced types.
- Check startup logs for schema parsing or validation errors.
- Check whether properties are overridden by profiles or environment variables.

### 9.4. Check the Web Application Type

If the GraphQL runtime exists but the HTTP endpoint is not registered, inspect the web stack:

- Does the project have the appropriate Spring MVC or WebFlux dependency?
- Were both stacks accidentally placed on the classpath, causing Boot to select an unexpected application type?
- Does **spring.main.web-application-type** override the application type?
- Is there a custom endpoint or path property?
- Is an exclusion disabling transport configuration?

Do not edit resolvers or schemas when the root cause actually lies in the transport.

## 10. Small GraphQL Application Configuration Example

Suppose you are building a book lookup API. The application needs a schema, a controller, and a configuration file.

Structure:

~~~text
src/
├── main/
│   ├── java/com/example/catalog/
│   │   ├── CatalogApplication.java
│   │   ├── BookController.java
│   │   └── BookService.java
│   └── resources/
│       ├── application.yml
│       └── graphql/
│           └── schema.graphqls
└── test/
    └── java/com/example/catalog/
~~~

Schema:

~~~graphql
type Book {
    id: ID!
    title: String!
}

type Query {
    book(id: ID!): Book
}
~~~

Configuration:

~~~yaml
spring:
  graphql:
    path: /graphql
    schema:
      locations: classpath:graphql/
~~~

Controller:

~~~java
@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    Book book(@Argument String id) {
        return bookService.findById(id);
    }
}
~~~

The application starts via **SpringApplication.run(...)**. Spring Boot detects the starter and required dependencies, loads the schema, builds the GraphQL runtime, binds the controller to fields, and registers the corresponding transport.

Clients can send:

~~~graphql
query FindBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
~~~

Variables:

~~~json
{
    "id": "book-42"
}
~~~

Remember that the configuration file only adjusts infrastructure; the schema defines the API contract; and controllers and services provide business behavior. Auto-configuration assembles those pieces into an application capable of accepting and executing GraphQL requests.

## 11. Common Issues

| Symptom | Common Cause | What to Check |
| --- | --- | --- |
| No GraphQL endpoint | Missing starter, missing web stack, or auto-configuration excluded | Check dependency tree and condition report |
| Schema not loaded | Wrong file location, wrong extension, or invalid location property | Check **spring.graphql.schema.*** and startup logs |
| Field in SDL returns no data | Unregistered DataFetcher/controller mapping or resolver error | Check **@QueryMapping**, **@SchemaMapping**, and services |
| Default bean does not appear | A custom bean caused **@ConditionalOnMissingBean** to back off | Check the context and condition report |
| GraphiQL inaccessible | Feature disabled or missing matching dependency/integration | Check properties and transport |
| Endpoint runs on wrong path | Property overridden by profile or environment variable | Check effective configuration |
| MVC/WebFlux behaves unexpectedly | Mismatched web application type or dependencies | Check classpath and **spring.main.web-application-type** |
| Boot upgrade alters auto-configuration | Conditions, properties, or registration mechanisms changed between versions | Read migration guide and inspect the new version's report |

## 12. Principles for Using Auto-configuration

When developing a Spring for GraphQL application, follow these principles:

1. Start with the starter compatible with your Spring Boot version.
2. Let Boot create the default infrastructure unless customization is needed.
3. Place schemas in the conventional resource location or configure locations explicitly.
4. Use **application.yml**/**application.properties** for supported configuration properties.
5. Use **@Controller**, **@QueryMapping**, and **@SchemaMapping** for field business behavior.
6. Use **RuntimeWiringConfigurer** and customizers when extending the GraphQL runtime.
7. Only replace a foundational bean once you understand everything the default bean handles.
8. Use the condition report to diagnose issues rather than guessing from an external symptom.
9. When upgrading Spring Boot, re-check properties, conditions, and auto-configuration discovery for the new version.
10. Write tests for both when configuration is applied and when Boot backs off because the application provides its own beans.

Auto-configuration reduces configuration boilerplate, but it does not replace understanding the architecture. Once you grasp classpaths, conditions, properties, beans, and extension points, you can customize your application deliberately while retaining the benefits of Spring Boot.

## 13. Summary

Spring Boot auto-configuration assembles beans and infrastructure based on dependencies on the classpath, properties, and existing beans. With Spring for GraphQL, this mechanism loads schemas, builds the GraphQL runtime, wires resolvers, and configures the transport suited to the application.

Applications usually only need to add the starter, place schemas in resources, declare controllers, and set necessary properties. When extending behavior, prefer dedicated extension points such as **RuntimeWiringConfigurer**, **GraphQlSourceBuilderCustomizer**, or properly conditioned beans. The condition evaluation report and tests with **ApplicationContextRunner** verify why configurations are applied or back off.

Understanding how Boot decides which configurations to activate is the foundation for building, customizing, and troubleshooting a reliable Spring for GraphQL application.
