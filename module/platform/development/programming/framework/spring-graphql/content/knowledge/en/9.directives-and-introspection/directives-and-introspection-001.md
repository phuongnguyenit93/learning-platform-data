# What Is a Directive in GraphQL?

A directive is a named instruction that can accept arguments and be attached to locations permitted by GraphQL. Directives add semantics to a schema or operation: they can mark a field as deprecated, describe a scalar's serialization standard, control field selection in a query, or trigger custom server-side logic.

In GraphQL SDL, directives are identified by the `@` symbol. GraphQL defines several built-in directives such as `@include`, `@skip`, `@deprecated`, and `@specifiedBy`. Applications can also declare custom directives to describe business rules or extend how the schema behaves. In Spring for GraphQL, custom schema directives are typically implemented using `RuntimeWiringConfigurer` and GraphQL Java's `SchemaDirectiveWiring`.

After this lesson, you will be able to:

- Explain what a directive is and how it differs from a field, argument, or resolver.
- Distinguish between directives on executable documents and directives on the schema type system.
- Read directive declaration syntax, arguments, default values, `repeatable`, and locations.
- Use the built-in directives `@include`, `@skip`, `@deprecated`, and `@specifiedBy`.
- Declare custom directives in SDL and understand why declaring one does not create behavior by itself.
- Register `SchemaDirectiveWiring` in Spring for GraphQL.
- Recognize security limitations, testing practices, and common pitfalls when designing directives.

## 1. Directives Add Semantics to GraphQL

A field in a schema specifies what data clients can request. A directive adds information or instructions to a part of the schema or an operation. For example:

```graphql
type Book {
    id: ID!
    title: String!
    oldTitle: String @deprecated(reason: "Use title instead.")
}
```

`@deprecated` marks `oldTitle` as no longer recommended for use. The field still exists in the schema and older clients can still query it; documentation tools or introspection can report that the field is deprecated.

Another example appears in an operation:

```graphql
query BookDetails($withAuthor: Boolean!) {
    book(id: "book-42") {
        title
        author @include(if: $withAuthor) {
            name
        }
    }
}
```

`@include` determines whether the `author` field is included in this execution, based on the `withAuthor` variable. A directive is neither a new field nor a resolver. It is an instruction attached to a location defined by GraphQL.

Directives can serve many purposes:

- **Metadata:** describing deprecated fields or which specification a custom scalar conforms to.
- **Operation control:** including or skipping fields/fragments based on variables.
- **Runtime behavior:** changing how a schema field is executed, such as formatting a value or applying an implemented policy.
- **Conventions and tooling:** providing metadata for code generation, validation, or documentation processing.

Not every directive automatically changes query execution results. Behavior depends on built-in directives executed by GraphQL or custom directive implementations registered by the application.

## 2. Two Groups of Directive Locations

GraphQL has two main groups of directive locations.

**Executable directives** are attached to operations, fields, fragments, or variable definitions in a GraphQL document. They affect how an operation is validated or executed. `@include` and `@skip` are two built-in examples.

```graphql
query FindBook($id: ID!, $showAuthor: Boolean!) {
    book(id: $id) {
        id
        title
        author @include(if: $showAuthor) {
            name
        }
    }
}
```

**Type-system directives** are attached to schema definitions in SDL, such as objects, field definitions, enum values, or scalars. `@deprecated` and `@specifiedBy` are built-in examples.

```graphql
scalar DateTime @specifiedBy(url: "https://example.org/date-time-format")

type Book {
    id: ID!
    oldTitle: String @deprecated(reason: "Use title instead.")
    title: String!
}
```

Both groups use the `@name` syntax, but they are processed at different stages. GraphQL Java's `SchemaDirectiveWiring` is designed to process directives attached to SDL schema elements. It does not automatically implement custom directives that appear in executable documents.

## 3. Directive Declaration Syntax

A custom directive is declared using the `directive` keyword, followed by the directive name, an optional list of arguments, and the allowed locations:

```graphql
directive @uppercase on FIELD_DEFINITION
```

The declaration above creates a directive named `uppercase`, which can only be attached to field definitions in the schema. It can be used as follows:

```graphql
type Book {
    title: String! @uppercase
}
```

A directive can accept arguments:

```graphql
directive @formatDate(pattern: String = "yyyy-MM-dd") on FIELD_DEFINITION

type AuditEvent {
    occurredAt: String! @formatDate(pattern: "dd/MM/yyyy")
}
```

`pattern` is an argument of the directive and has a default value if not provided. Directive arguments use GraphQL input types such as scalars, enums, lists, or input objects; output object types are not allowed.

A directive can also be declared as `repeatable` if you want to allow it to be attached multiple times at the same location:

```graphql
directive @tag(name: String!) repeatable on FIELD_DEFINITION

type Book {
    title: String! @tag(name: "searchable") @tag(name: "public")
}
```

Without the `repeatable` keyword, the same directive cannot be repeated multiple times at the same location. `repeatable` only permits repetition; the meaning of multiple applications and how arguments are combined are still determined by the directive implementation.

## 4. Directive Locations

The `on` clause in the declaration specifies where the directive can be placed. Location names are case-sensitive values. Common locations include:

| Group | Location | Applied Position |
| --- | --- | --- |
| Executable | `QUERY` | Query operation |
| Executable | `MUTATION` | Mutation operation |
| Executable | `SUBSCRIPTION` | Subscription operation |
| Executable | `FIELD` | Field in an operation |
| Executable | `FRAGMENT_DEFINITION` | Named fragment definition |
| Executable | `FRAGMENT_SPREAD` | Location where a named fragment is spread |
| Executable | `INLINE_FRAGMENT` | Inline fragment |
| Executable | `VARIABLE_DEFINITION` | Variable declaration in an operation |
| Type system | `SCHEMA` | Schema definition |
| Type system | `SCALAR` | Scalar definition |
| Type system | `OBJECT` | Object type definition |
| Type system | `FIELD_DEFINITION` | Field of an object or interface |
| Type system | `ARGUMENT_DEFINITION` | Argument of a field or directive |
| Type system | `INTERFACE` | Interface definition |
| Type system | `UNION` | Union definition |
| Type system | `ENUM` | Enum definition |
| Type system | `ENUM_VALUE` | An enum value |
| Type system | `INPUT_OBJECT` | Input object definition |
| Type system | `INPUT_FIELD_DEFINITION` | Field of an input object |

Example of a directive allowed on objects and fields:

```graphql
directive @requiresAuthentication on OBJECT | FIELD_DEFINITION
```

Declaring locations does not automatically apply the directive to every object or field. It only defines the valid locations where the directive can be used. If a client or schema places a directive in an unpermitted location, the schema/document will be invalid.

## 5. Common Built-in Directives

GraphQL defines several built-in directives. These directives already have meaning in the GraphQL runtime; applications do not need to write `SchemaDirectiveWiring` for them to work.

### `@include`

`@include(if: Boolean!)` includes a field or fragment in execution only when the `if` argument is `true`:

```graphql
query Book($id: ID!, $withReviews: Boolean!) {
    book(id: $id) {
        title
        reviews @include(if: $withReviews) {
            rating
            comment
        }
    }
}
```

If `$withReviews` is `false`, the `reviews` field is skipped in that execution.

### `@skip`

`@skip(if: Boolean!)` skips a field or fragment when `if` is `true`:

```graphql
query Book($id: ID!, $hideInternal: Boolean!) {
    book(id: $id) {
        title
        internalNotes @skip(if: $hideInternal)
    }
}
```

If `$hideInternal` is `true`, the `internalNotes` field is not selected in the operation.

`@include` and `@skip` can be used on fields, fragment spreads, and inline fragments. If both directives are present at the same location, the field is executed only when the include condition is true and the skip condition is false. They are not an authorization mechanism: clients can still send operations requesting sensitive fields directly.

### `@deprecated`

`@deprecated` marks a field or enum value in the schema as no longer recommended:

```graphql
enum PaymentMethod {
    CARD
    BANK_TRANSFER
    CASH @deprecated(reason: "Use an electronic payment method.")
}

type Book {
    id: ID!
    authorName: String @deprecated(reason: "Use author { name } instead.")
    author: Author
}
```

The `reason` argument has a default value if omitted. This directive provides metadata for introspection and developer tools; it does not automatically block queries or mutations that use the deprecated field/value. If you want to discontinue support, you need a compatibility plan and an appropriate removal policy.

### `@specifiedBy`

`@specifiedBy(url: String!)` attaches a specification URL to a custom scalar:

```graphql
scalar DateTime @specifiedBy(url: "https://example.org/specs/date-time")
```

The directive helps clients and tools understand which format the scalar follows. It does not parse, validate, or serialize `DateTime` values by itself; the application still needs to register the custom scalar with corresponding coercing logic.

## 6. Declaring Custom Schema Directives

Custom directives allow expressing application-specific conventions in SDL. For example, a schema might want to mark a field as requiring the `ADMIN` role:

```graphql
enum Role {
    USER
    EDITOR
    ADMIN
}

directive @requiresRole(role: Role!) on FIELD_DEFINITION

type Query {
    publicBooks: [Book!]!
    moderationQueue: [Book!]! @requiresRole(role: ADMIN)
}
```

The SDL describes that `moderationQueue` has the `requiresRole` directive with the `role` argument set to `ADMIN`. However, merely declaring a directive and attaching it to a field does not enforce permissions. Without runtime wiring or another mechanism that reads the directive and enforces the policy, this annotation is only metadata.

Custom directives can be used for:

- Authorization rules or policy metadata.
- Formatting, normalizing, or transforming field values.
- Cache hints or control information for gateways.
- Validation metadata, such as limits or formats.
- Integration with documentation generators or code generation tools.

You should only create a directive when it expresses a meaningful rule and has a clear place where it is enforced or consumed. If a directive only makes the schema harder to read with no consumer handling it, it provides no useful behavior.

## 7. Implementing Schema Directives in Spring for GraphQL

Spring for GraphQL uses GraphQL Java to build the executable schema. Custom directives can be registered using `RuntimeWiringConfigurer`; Spring Boot automatically detects this bean and includes it in the `GraphQlSource` configuration process.

`SchemaDirectiveWiring` provides callbacks for schema elements such as objects, fields, arguments, scalars, enums, and input objects. When a directive is attached to a field, `onField` can inspect the field definition and alter runtime behavior, such as wrapping the existing `DataFetcher`.

For example, an `@uppercase` directive converts the returned string to uppercase.

SDL:

```graphql
directive @uppercase on FIELD_DEFINITION

type Query {
    greeting: String!
}
```

Java implementation:

```java
public class UppercaseDirective implements SchemaDirectiveWiring {

    @Override
    public GraphQLFieldDefinition onField(
            SchemaDirectiveWiringEnvironment<GraphQLFieldDefinition> environment) {

        GraphQLFieldDefinition field = environment.getElement();
        GraphQLFieldsContainer parentType = environment.getFieldsContainer();

        DataFetcher<?> originalFetcher = environment.getCodeRegistry()
                .getDataFetcher(parentType, field);

        DataFetcher<?> wrappedFetcher = DataFetcherFactories.wrapDataFetcher(
                originalFetcher,
                (dataFetchingEnvironment, value) -> {
                    if (value instanceof String text) {
                        return text.toUpperCase(Locale.ROOT);
                    }
                    return value;
                });

        FieldCoordinates coordinates = FieldCoordinates.coordinates(parentType, field);
        environment.getCodeRegistry().dataFetcher(coordinates, wrappedFetcher);

        return field;
    }
}
```

Registering the directive in Spring configuration:

```java
@Configuration
public class GraphQlConfiguration {

    @Bean
    RuntimeWiringConfigurer runtimeWiringConfigurer() {
        return builder -> builder.directive(
                "uppercase",
                new UppercaseDirective());
    }
}
```

Placing the directive on the field to transform:

```graphql
type Query {
    greeting: String! @uppercase
}
```

The corresponding Spring resolver can be very simple:

```java
@Controller
public class GreetingController {

    @QueryMapping
    public String greeting() {
        return "hello graphql";
    }
}
```

If the resolver returns `"hello graphql"`, the `greeting` response field will be `"HELLO GRAPHQL"`. `DataFetcherFactories.wrapDataFetcher` helps wrap the existing data fetcher and handles both synchronous values and `CompletionStage` instances returned by the data fetcher.

This example illustrates custom behavior for a schema field. In real-world applications, transformation logic should be placed in the appropriate layer, return types should be checked, and directives should not be used to hide complex business rules. If multiple directives wrap the same field, their ordering and how they compose must be clearly defined.

## 8. Reading Custom Directive Arguments

Directive arguments can configure behavior per field. For example, `@dateFormat` accepts a pattern:

```graphql
directive @dateFormat(pattern: String = "yyyy-MM-dd") on FIELD_DEFINITION

type AuditEvent {
    occurredAt: String! @dateFormat(pattern: "dd/MM/yyyy")
}
```

In `SchemaDirectiveWiring`, you can read the directive applied to a schema element through the environment and use that argument to configure a wrapper or runtime metadata. GraphQL Java provides the corresponding applied directive APIs; the exact API names may vary depending on the GraphQL Java version in use.

A directive like `@dateFormat` can do one of two things:

1. Simply provide metadata for another layer to read and use.
2. Alter schema/runtime behavior by wrapping or replacing the data fetcher, adding arguments, or applying another processing mechanism.

Merely defining `pattern` in SDL does not format dates automatically. The wiring must read the value and apply a formatter; otherwise, the response retains the field's default serialization.

## 9. Schema Directives vs. Executable Directives in Applications

A common point of confusion is that both types share the same directive syntax but are processed in two different places:

| Aspect | Schema Directive | Executable Directive |
| --- | --- | --- |
| Where it is placed | SDL schema definition | Query, mutation, subscription, field, or fragment in an operation |
| Examples | `@deprecated`, `@specifiedBy`, `@requiresRole` | `@include`, `@skip` |
| Purpose | Add metadata or alter runtime schema | Control a client's specific operation |
| Common mechanism | `SchemaDirectiveWiring`, `RuntimeWiringConfigurer` | GraphQL execution engine; custom behavior needs integration into the execution pipeline |
| Runs automatically when merely declared? | Custom directives require implementation | Custom executable directives require implementation; built-in directives are supported by the runtime |

Do not expect `SchemaDirectiveWiring` to handle a custom directive attached in a query document. That callback operates on SDL schema elements. For custom executable directives, choose an appropriate GraphQL Java extension mechanism and verify compatibility with your Spring for GraphQL version.

## 10. Directives and Security

Directives can describe policies, but a line of SDL is not a security boundary. For example:

```graphql
directive @requiresRole(role: Role!) on FIELD_DEFINITION

type Query {
    payrollRecords: [PayrollRecord!]! @requiresRole(role: ADMIN)
}
```

If `@requiresRole` has not been implemented and wired to an authentication/authorization mechanism, any user able to invoke the field can receive data through existing resolvers. Even when a directive is wired, ensure authorization checks rely on the request's principal and context, not on a value sent by the client.

Several principles:

- Protect fields or services with Spring Security/method security or an equivalent authorization mechanism.
- Check permissions on specific records if access depends on owner, tenant, or data relationships.
- Do not treat `@include` or `@skip` as a mechanism for hiding data; clients can omit the directive and request the field directly.
- Do not let error messages leak sensitive information about policies or internal data.
- Test both authorized and unauthorized users, including access through nested fields.

If a directive is used as a metadata source for authorization, ensure every access path to the field is protected, including resolvers invoked through fragments, aliases, or other operations.

## 11. Discovering Directives with Introspection

GraphQL introspection allows clients to discover directives defined in the schema via `__schema.directives`. For example:

```graphql
query ListDirectives {
    __schema {
        directives {
            name
            description
            isRepeatable
            locations
            args {
                name
                description
                defaultValue
                type {
                    kind
                    name
                    ofType {
                        kind
                        name
                    }
                }
            }
        }
    }
}
```

The returned information tells tools the directive name, description, valid locations, whether the directive is repeatable, and the arguments it accepts. This is information about directive definitions in the schema. You should not assume standard introspection will list every place a custom directive has been applied; the ability to discover applied directives depends on the specification version, GraphQL Java, and related tools.

For fields or enum values marked as deprecated, introspection exposes fields such as `isDeprecated` and `deprecationReason`. Some introspection lists hide deprecated elements by default; you can explicitly request them with the `includeDeprecated` argument when querying fields or enum values, where supported by the introspection location.

In Spring Boot, introspection is typically enabled by default to support tools such as GraphiQL. You can configure introspection policies per environment. Disabling introspection reduces public schema discoverability, but it does not replace authorization for data fields.

## 12. Testing Directives

Directives need to be tested at both layers: whether the schema declares the directive properly and whether the runtime executes the expected behavior.

For the `@uppercase` directive, you can use `GraphQlTester` to send a query:

```java
graphQlTester.document("""
        query {
            greeting
        }
        """)
    .execute()
    .path("greeting")
    .entity(String.class)
    .isEqualTo("HELLO GRAPHQL");
```

Cases that should be tested:

1. The schema initializes successfully when the directive is declared at a valid location.
2. The schema is rejected if the directive is placed at an unpermitted location.
3. Custom directive wiring is invoked on the exact fields where the directive is applied.
4. Fields without the directive retain their default behavior.
5. Both synchronous and asynchronous values are handled properly by the wrapper.
6. Directive arguments and default values are applied accurately.
7. Repeatable directives are processed according to the ordering/rules published by the application.
8. Directives used for authorization reject unauthorized users.
9. `@include` and `@skip` work based on variables; they do not change access permissions.
10. Introspection returns directive definitions and deprecation metadata as expected.

## 13. Common Pitfalls

- **Assuming declaring a directive creates behavior automatically:** SDL only describes the name, arguments, and locations; custom directives require implementation.
- **Using an invalid location:** directives may only be placed at the locations listed after `on`.
- **Confusing schema directives with executable directives:** `SchemaDirectiveWiring` handles directives attached in SDL, not custom directives on operation documents.
- **Using `@deprecated` to block a field:** the directive only marks metadata and does not reject requests.
- **Using `@include` or `@skip` for authorization:** clients control variables and can omit the directive.
- **Forgetting to handle async DataFetchers:** custom wrappers may break `CompletionStage` handling; use an appropriate helper such as `DataFetcherFactories.wrapDataFetcher`.
- **Failing to define ordering for multiple directives:** multiple wrappers can affect each other without clear rules.
- **Overusing directives for every rule:** complex business logic usually belongs in dedicated services or policy components.
- **Assuming introspection lists every directive application:** standard introspection primarily provides directive definitions and supported metadata.

## 14. Workflow for Designing a Custom Directive

When extending GraphQL with a directive, follow this sequence:

1. Determine whether the directive belongs to executable documents or the schema type system.
2. Decide whether the goal is metadata or altering runtime behavior.
3. Declare the name, arguments, default values, `repeatable`, and locations in SDL.
4. Write descriptions so schema consumers understand the directive's meaning and limitations.
5. For schema directives, implement `SchemaDirectiveWiring` and register it via `RuntimeWiringConfigurer`.
6. For custom executable directives, choose an appropriate execution pipeline integration mechanism for GraphQL Java.
7. Verify interactions with resolvers, async results, errors, authorization, and other directives.
8. Write tests for schema validation, runtime behavior, and introspection.
9. Document compatibility impacts if changing or removing a published directive.

Directives are GraphQL's structured extension mechanism. Built-in directives provide common behaviors and metadata; custom directives allow applications to express domain-specific conventions. In Spring for GraphQL, connect schema directives to `SchemaDirectiveWiring` via runtime wiring, test real behavior, and keep security rules on the server. When each directive has a clear purpose and enforcement point, the schema becomes richer in semantics while remaining easy to understand and maintain.

## References

- [GraphQL Specification — Type System Directives](https://spec.graphql.org/October2021/#sec-Type-System.Directives)
- [GraphQL Specification — Executable Directives](https://spec.graphql.org/October2021/#sec-Directives)
- [Spring for GraphQL — Request Execution, RuntimeWiringConfigurer and Directives](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [GraphQL Java — SDL Directives](https://graphql-java.com/documentation/directives/)
- [GraphQL Java — SchemaDirectiveWiring API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/schema/idl/SchemaDirectiveWiring.html)
