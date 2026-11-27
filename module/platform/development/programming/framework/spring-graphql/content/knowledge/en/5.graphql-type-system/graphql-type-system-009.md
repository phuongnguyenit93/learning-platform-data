# Schema directives in GraphQL

A **directive** is a GraphQL construct used to attach instructions or metadata to schemas and operations. Directives have names starting with `@`, can accept arguments, and may only be placed at locations permitted by their definition. Familiar examples include `@include` and `@skip` in queries and `@deprecated` in schemas.

In Spring for GraphQL, directives belong to the GraphQL type system and are declared in SDL. GraphQL Java executes built-in directives automatically; custom directives require the application to register handling logic through schema-building mechanisms such as `RuntimeWiringConfigurer` and `SchemaDirectiveWiring`.

## 1. Structure of a directive

A directive has three main components:

- **Name:** an identifier starting with `@`, such as `@deprecated` or `@requiresRole`.
- **Arguments:** configuration data for the directive, such as `if: Boolean!` or `role: Role!`.
- **Locations:** places where the directive is allowed to appear, such as `FIELD`, `OBJECT`, or `FIELD_DEFINITION`.

Both built-in directives and custom directives follow this structure. In SDL, a custom directive must be defined before it is applied:

```graphql
enum Role {
    USER
    ADMIN
}

directive @requiresRole(role: Role!) on FIELD_DEFINITION

type Query {
    publicMessage: String
    adminReport: String @requiresRole(role: ADMIN)
}
```

The `directive @requiresRole...` declaration specifies the name, arguments, and valid locations. Attaching `@requiresRole(role: ADMIN)` to `adminReport` adds metadata to the schema. That SDL line alone does not authenticate users; the application must implement the corresponding behavior.

## 2. Directive locations

Locations specify where a directive can be applied. The two common categories of locations are:

| Category | Typical locations | Meaning |
|---|---|---|
| Schema/type system | `SCHEMA`, `SCALAR`, `OBJECT`, `FIELD_DEFINITION`, `ARGUMENT_DEFINITION`, `INTERFACE`, `UNION`, `ENUM`, `ENUM_VALUE`, `INPUT_OBJECT`, `INPUT_FIELD_DEFINITION` | Attaches instructions or metadata to schema definitions. |
| Executable document | `QUERY`, `MUTATION`, `SUBSCRIPTION`, `FIELD`, `FRAGMENT_DEFINITION`, `FRAGMENT_SPREAD`, `INLINE_FRAGMENT`, `VARIABLE_DEFINITION` | Attaches instructions to operations, fields, fragments, or variables in a request. |

Example of a directive that applies only to fields in the schema:

```graphql
directive @upperCase on FIELD_DEFINITION
```

This directive can be used as follows:

```graphql
type Product {
    name: String @upperCase
}
```

You cannot arbitrarily place `@upperCase` on a query field if the directive only declares `FIELD_DEFINITION`. If a directive should be usable in operations, it must declare the corresponding location, such as `FIELD`.

## 3. Built-in directives in operations

### `@include`

`@include(if: Boolean!)` instructs GraphQL to include a field or fragment in the result only if the `if` expression evaluates to `true`.

```graphql
query ProductDetail($showDescription: Boolean!) {
    product(id: "p-100") {
        id
        name
        description @include(if: $showDescription)
    }
}
```

If `$showDescription` is `false`, the `description` field is skipped during execution. Clients can use this directive to select fields based on UI needs.

### `@skip`

`@skip(if: Boolean!)` has the opposite effect: it skips a field or fragment when `if` is `true`.

```graphql
query ProductDetail($hidePrice: Boolean!) {
    product(id: "p-100") {
        id
        name
        price @skip(if: $hidePrice)
    }
}
```

If `$hidePrice` is `true`, GraphQL does not execute the `price` selection in that operation. Both `@include` and `@skip` are handled natively by GraphQL; there is no need to write resolvers or register custom directives in Spring.

These directives can be used on `FIELD`, `FRAGMENT_SPREAD`, and `INLINE_FRAGMENT`. If a selection carries both `@include` and `@skip`, the field is executed only when the include condition is true and the skip condition is false.

## 4. Built-in directives in schemas

### `@deprecated`

`@deprecated` marks an older field or enum value and recommends that clients migrate to a replacement API. The directive accepts a `reason` argument; if omitted, the default reason is `No longer supported`.

```graphql
type Product {
    id: ID!
    oldCode: String @deprecated(reason: "Use sku instead")
    sku: String!
}

enum OrderStatus {
    NEW
    PROCESSING
    OLD_DONE @deprecated(reason: "Use COMPLETED")
    COMPLETED
}
```

`@deprecated` does not remove the field from the schema, nor does it block clients from calling it. It publishes deprecation status so GraphQL tools, API documentation, and clients can warn or assist with migration. This metadata can be queried via introspection—such as `isDeprecated` and `deprecationReason` on fields or enum values; when listing them, request deprecated items using the corresponding introspection arguments.

Some GraphQL versions also support marking arguments or input fields as deprecated. Check the GraphQL Java version in use before applying the directive at those locations.

### `@specifiedBy`

`@specifiedBy(url: String!)` attaches a URL pointing to the specification of a custom scalar. Example:

```graphql
scalar DateTime @specifiedBy(url: "https://scalars.graphql.org/andimarek/date-time")
```

The directive provides documentation so schema consumers understand the format and rules of the `DateTime` scalar. It does not implement a parser or serializer for the scalar by itself. The application must still configure the corresponding scalar to convert data between its GraphQL representation and Java types.

## 5. Defining custom directives

Custom directives are useful when you need to attach metadata or shared behavior across multiple parts of a schema. General syntax:

```graphql
directive @directiveName(argument: Type) on LOCATION
```

Example directive describing data that must be masked in logs:

```graphql
directive @sensitive on FIELD_DEFINITION

type Customer {
    id: ID!
    name: String!
    email: String @sensitive
    phone: String @sensitive
}
```

The schema indicates that `email` and `phone` are sensitive fields. The application can read that metadata in logging or instrumentation logic to avoid writing raw values to logs. Without implementation code that reads and acts on the directive, `@sensitive` is purely schema metadata.

### Directives with arguments

Arguments allow a directive to be configured differently at each usage site:

```graphql
directive @mask(visibleCharacters: Int! = 2) on FIELD_DEFINITION

type Customer {
    email: String @mask(visibleCharacters: 3)
    phone: String @mask(visibleCharacters: 2)
}
```

Argument values can have defaults. In this example, `visibleCharacters` defaults to `2`, while the `email` field overrides it to `3`. Argument data types and values must still conform to GraphQL rules.

### `repeatable` directives

By default, a directive cannot be repeated multiple times at the same location. Add the `repeatable` keyword when multiple applications are needed:

```graphql
directive @tag(name: String!) repeatable on OBJECT | FIELD_DEFINITION

type Product @tag(name: "catalog") @tag(name: "searchable") {
    name: String @tag(name: "display")
}
```

`repeatable` allows multiple occurrences of the same directive at one location. If a directive is not declared `repeatable`, applying it multiple times at the same location causes a schema or document validation error.

## 6. Handling custom directives in Spring for GraphQL

Spring for GraphQL uses GraphQL Java to build and execute the schema. With schema-first development, you can register directive handling through `RuntimeWiringConfigurer` and `SchemaDirectiveWiring`.

For example, an `@upperCase` directive converts the string value returned by a data fetcher to uppercase:

```graphql
directive @upperCase on FIELD_DEFINITION

type Query {
    greeting: String @upperCase
}
```

A standard resolver:

```java
@Controller
class GreetingController {

    @QueryMapping
    String greeting() {
        return "hello graphql";
    }
}
```

Registering the directive during runtime wiring configuration:

```java
@Configuration
class GraphQlDirectiveConfiguration {

    @Bean
    RuntimeWiringConfigurer directiveConfigurer() {
        return wiringBuilder -> wiringBuilder.directive(
            "upperCase",
            new UpperCaseDirectiveWiring()
        );
    }
}
```

The `SchemaDirectiveWiring` implementation can wrap the existing data fetcher:

```java
class UpperCaseDirectiveWiring implements SchemaDirectiveWiring {

    @Override
    public GraphQLFieldDefinition onField(
            SchemaDirectiveWiringEnvironment<GraphQLFieldDefinition> environment) {

        GraphQLFieldDefinition field = environment.getElement();
        DataFetcher<?> originalFetcher = environment.getCodeRegistry()
            .getDataFetcher(environment.getFieldsContainer(), field);

        DataFetcher<?> upperCaseFetcher = DataFetcherFactories.wrapDataFetcher(
            originalFetcher,
            (dataFetchingEnvironment, value) -> {
                if (value instanceof String) {
                    return ((String) value).toUpperCase(Locale.ROOT);
                }
                return value;
            }
        );

        environment.getCodeRegistry().dataFetcher(
            environment.getFieldsContainer(), field, upperCaseFetcher);
        return field;
    }
}
```

This example focuses on the idea of wrapping a data fetcher: the directive is read from the schema, retrieves the existing data fetcher, and adds a post-processing step before GraphQL returns the data. Imports are omitted to focus on the core logic; exact API details may vary with the GraphQL Java version managed by Spring for GraphQL. Check your project's dependency version when implementing.

A few points to keep in mind when applying this:

1. The name passed to `wiringBuilder.directive("upperCase", ...)` must match the directive name in the SDL, without the `@` character.
2. Only wrap data fetchers at locations where the directive is declared and handled accordingly.
3. Preserve the original data fetcher's behavior, including exceptions and asynchronous return types.
4. If the directive has arguments, read the argument values from the directive in `SchemaDirectiveWiringEnvironment` and validate the configuration before creating the wrapper.
5. Do not register custom directive handlers for built-in directives such as `@include` or `@skip`; GraphQL Java already handles them.

## 7. Directives and security

A directive such as `@requiresRole(role: ADMIN)` can make the schema easier to read and express security intent right next to a field:

```graphql
directive @requiresRole(role: Role!) on FIELD_DEFINITION

type Query {
    publicCatalog: [Product!]!
    adminReport: Report @requiresRole(role: ADMIN)
}
```

However, declaring a directive does not automatically enforce access control. If the application only adds `@requiresRole` to the SDL without registering an enforcement mechanism, users can still call the field under existing resolver behavior.

In a Spring application, permissions can be enforced at the resolver layer with Spring Security, for example. The snippet assumes method security is enabled via `@EnableMethodSecurity` and `ReportService` is injected into the controller:

```java
@Controller
class ReportController {

    @QueryMapping
    @PreAuthorize("hasRole('ADMIN')")
    Report adminReport() {
        return reportService.loadReport();
    }
}
```

If you want directives to serve as the metadata source for centralized policy enforcement, write a `SchemaDirectiveWiring` or equivalent mechanism to connect the metadata to actual permission checks. When doing so, cover nested fields, mutations, and subscriptions as well; do not allow an alternate access path to bypass the policy. Also establish clearly whether the principal and authorities are obtained from the Spring Security context or `GraphQLContext`.

For applications with many security rules, Spring Security method security or a dedicated authorization layer is often easier to test and audit. Directives can supplement the schema with metadata, but they should never be treated as a protection mechanism merely because they appear in the SDL.

## 8. Distinguishing directives from arguments and Java annotations

| Component | Role | Example |
|---|---|---|
| GraphQL argument | Value passed by the client when calling a field | `product(id: ID!)` |
| GraphQL directive | Instruction or metadata attached to schema/operation | `email @deprecated` or `field @include(if: $show)` |
| Java annotation | Metadata/behavior in Java source code, processed by the framework or application | `@QueryMapping`, `@SchemaMapping`, `@PreAuthorize` |

`@SchemaMapping` is a Spring for GraphQL annotation for mapping a Java method to a schema field. It is not a GraphQL directive and is not declared in SDL. Conversely, `@deprecated` or custom directives are declared and applied in GraphQL SDL.

## 9. Testing directives

Tests should reflect the exact role of each type of directive:

- For `@include` and `@skip`, send operations with both `true` and `false` variable values and verify that the field appears or is omitted in `data` conditionally.
- For `@deprecated`, inspect metadata via schema introspection and verify that the old field continues to work during the compatibility window if that is the API policy.
- For `@specifiedBy`, verify that the scalar publishes the specification URL and that the scalar's parser/serializer handles data properly.
- For custom directives such as `@upperCase`, send a query to the annotated field and verify that the data fetcher wrapper produces the expected result.
- For directives describing permissions, test both authorized and unauthorized users. Also verify that the resolver is not invoked when a request is denied.

`GraphQlTester` can send GraphQL documents, pass variables, and assert on responses. When testing schema directives or metadata, you can use introspection or inspect the configured schema directly in the test context. Do not merely check that the SDL contains `@requiresRole`; test the actual runtime behavior of the policy enforcement layer.

## 10. Common mistakes

**Using the wrong location.** For example, declaring a directive only for `FIELD_DEFINITION` and applying it to a `FIELD` in a query. Check both the directive definition's locations and the usage site.

**Forgetting to define a custom directive.** A directive unknown to GraphQL can make the schema invalid. Declare the directive in SDL or provide it through the appropriate schema mechanism before applying it.

**Assuming custom directives run automatically.** SDL only describes the directive. The application must register `SchemaDirectiveWiring`, instrumentation, or a metadata-reading mechanism.

**Naming a directive after a built-in directive.** Do not redefine `@skip`, `@include`, `@deprecated`, or `@specifiedBy` with custom application behavior.

**Using directives as the sole security layer.** Metadata does not block requests on its own. Real authorization checks must exist and all access paths must be tested.

**Not checking version compatibility.** Some GraphQL Java locations or APIs can differ across versions. Check the dependency managed by Spring Boot before using newer features.

## Conclusion

Directives extend GraphQL's expressive power by attaching instructions and metadata to schemas or operations. Built-in directives such as `@include`, `@skip`, `@deprecated`, and `@specifiedBy` have behavior supported out of the box by GraphQL. Custom directives require defining locations, arguments, and registering handling logic in the application. When using them with Spring for GraphQL, keep a clear distinction between metadata in the SDL and the actual behavior of data fetchers, resolvers, and the security layer.
