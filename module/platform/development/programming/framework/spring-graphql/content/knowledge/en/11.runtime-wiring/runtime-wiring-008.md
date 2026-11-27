# Directive wiring

A directive is a GraphQL feature used to attach instructions or metadata to schemas and operations. A directive's name starts with the **@** character, can accept arguments, and may only be placed in locations where it is permitted. For example, **@deprecated** marks an obsolete field; **@skip** and **@include** conditionally control whether a field is included in the response.

For custom directives, declaring them in SDL only describes the name, arguments, and valid locations. For a directive to trigger runtime behavior when the server executes, the application must connect it to runtime wiring. In Spring for GraphQL, that logic can be registered via **RuntimeWiringConfigurer** and GraphQL Java's **SchemaDirectiveWiring**.

This lesson focuses on declaring directives, distinguishing built-in directives from custom directives, understanding application locations, implementing schema directives with **SchemaDirectiveWiring**, integrating them into Spring Boot, and testing behavior after wiring.

## 1. What is a directive?

A directive is an annotation/instruction attached to a GraphQL element. General syntax:

~~~graphql
@directiveName
~~~

A directive can accept arguments:

~~~graphql
@directiveName(argument: value)
~~~

For example, GraphQL includes the standard **@deprecated** directive:

~~~graphql
type Book {
  id: ID!
  title: String!
  legacyCode: String @deprecated(reason: "Use id")
}
~~~

The **@deprecated** directive attaches metadata to the **legacyCode** field, indicating that clients should migrate to another field. Introspection tools and IDEs can display the deprecation reason to assist with migration.

Directives can be used in two groups of locations:

- **Schema locations:** attached to the schema definition, object types, field definitions, argument definitions, enum values, scalars, input objects, or other schema elements.
- **Executable locations:** attached to operations, field selections, fragments, variable definitions, and elements of GraphQL documents sent by clients.

The two groups have different lifecycles. Directives on schemas are typically processed when building the schema or read as metadata. Directives on operations are processed during the parse/validation/execution of the operation.

## 2. Defining a custom directive in SDL

To declare a custom directive, use the **directive** keyword:

~~~graphql
directive @uppercase on FIELD_DEFINITION
~~~

This declaration creates a directive named **uppercase**, which can only be attached to field definitions in the schema.

The directive can be applied on a field:

~~~graphql
type Book {
  id: ID!
  title: String! @uppercase
}
~~~

A directive can accept arguments:

~~~graphql
directive @format(pattern: String!) on FIELD_DEFINITION

type Book {
  publishedAt: String @format(pattern: "yyyy-MM-dd")
}
~~~

Directive arguments also have GraphQL types. You can use valid scalars, enums, or input types depending on the directive's locations and rules.

### Choosing directive locations

After the **on** keyword, declare the locations where the directive is permitted. A directive can support multiple locations separated by **|**:

~~~graphql
directive @audit on FIELD_DEFINITION | OBJECT
~~~

Common schema locations:

| Location | Applicable Element |
|---|---|
| **SCHEMA** | Schema definition |
| **SCALAR** | Scalar type |
| **OBJECT** | Object type |
| **FIELD_DEFINITION** | Field of an object or interface |
| **ARGUMENT_DEFINITION** | Argument of a field or directive |
| **INTERFACE** | Interface type |
| **UNION** | Union type |
| **ENUM** | Enum type |
| **ENUM_VALUE** | Enum value |
| **INPUT_OBJECT** | Input object |
| **INPUT_FIELD_DEFINITION** | Field of an input object |

Executable locations include **QUERY**, **MUTATION**, **SUBSCRIPTION**, **FIELD**, **FRAGMENT_DEFINITION**, **FRAGMENT_SPREAD**, **INLINE_FRAGMENT**, and **VARIABLE_DEFINITION**.

If a directive needs to be applied multiple times on the same location, declare **repeatable**:

~~~graphql
directive @tag(name: String!) repeatable on FIELD_DEFINITION

type Book {
  title: String! @tag(name: "searchable") @tag(name: "display")
}
~~~

Without the **repeatable** keyword, a directive cannot be repeated multiple times on the same location.

## 3. Built-in directives and custom directives

GraphQL defines several standard directives. These directives are understood by the GraphQL engine with predefined semantics:

| Directive | Typical Locations | Purpose |
|---|---|---|
| **@skip(if: Boolean!)** | FIELD, fragment | Skips the selection when the condition is true |
| **@include(if: Boolean!)** | FIELD, fragment | Includes the selection only when the condition is true |
| **@deprecated(reason: String)** | FIELD_DEFINITION, ENUM_VALUE | Marks a schema element as obsolete |
| **@specifiedBy(url: String!)** | SCALAR | Links a scalar to its specification document |

Example of an executable directive on an operation:

~~~graphql
query BookDetails($showDescription: Boolean!) {
  book(id: "book-01") {
    id
    title
    description @include(if: $showDescription)
  }
}
~~~

If the **showDescription** variable is false, the **description** field is omitted from the response. Clients can control the selection set without writing two separate queries.

Example of a metadata directive on a schema:

~~~graphql
type Book {
  id: ID!
  oldTitle: String @deprecated(reason: "Use title")
  title: String!
}
~~~

Custom directives can describe metadata or implement custom behavior—such as uppercasing, audit logging, formatting values, or enforcing a policy. GraphQL does not infer behavior for a custom directive merely from its name.

### Declaring a directive does not mean executing it

Example:

~~~graphql
directive @uppercase on FIELD_DEFINITION

type Book {
  title: String! @uppercase
}
~~~

The SDL above only states that **@uppercase** exists and is used on a field. If the server does not register directive-handling logic, the **title** value will not automatically be uppercased.

This is an important boundary:

- **SDL definition:** defines the name, arguments, repeatability, and locations.
- **Applied directive:** where the directive is attached to a type or field.
- **Runtime wiring:** the logic the server uses to apply the directive's behavior.

## 4. SchemaDirectiveWiring in GraphQL Java

GraphQL Java provides the **SchemaDirectiveWiring** interface to handle directives attached to schema elements. When the schema is built, GraphQL Java invokes the callback corresponding to the element type where the directive is applied.

Common callbacks:

| Callback | Schema element |
|---|---|
| **onField** | GraphQLFieldDefinition |
| **onArgument** | GraphQLArgument |
| **onObject** | GraphQLObjectType |
| **onInterface** | GraphQLInterfaceType |
| **onUnion** | GraphQLUnionType |
| **onEnum** | GraphQLEnumType |
| **onEnumValue** | GraphQLEnumValueDefinition |
| **onScalar** | GraphQLScalarType |
| **onInputObjectType** | GraphQLInputObjectType |
| **onInputObjectField** | GraphQLInputObjectField |

For directives on fields, the **onField** callback is typically used to inspect metadata and adjust the field's data fetcher. You can wrap the existing data fetcher to add behavior before or after the value is retrieved.

Key point to remember: **SchemaDirectiveWiring** is typically applied during schema construction. It is not a resolver replacement for the entire field, nor does it run automatically like an HTTP interceptor on every request.

## 5. Example: directive converting String values to uppercase

Suppose we want to declare the **@uppercase** directive to convert a field's returned String value to uppercase.

SDL:

~~~graphql
directive @uppercase on FIELD_DEFINITION

type Book {
  id: ID!
  title: String! @uppercase
}

type Query {
  book(id: ID!): Book
}
~~~

The existing resolver returns a `Book` whose title is **Spring GraphQL**. The directive wraps the data fetcher of the **Book.title** field and transforms the value after fetching.

Implementation:

~~~java
import graphql.schema.DataFetcher;
import graphql.schema.DataFetcherFactories;
import graphql.schema.GraphQLFieldDefinition;
import graphql.schema.idl.SchemaDirectiveWiring;
import graphql.schema.idl.SchemaDirectiveWiringEnvironment;

import java.util.Locale;

public class UppercaseDirective implements SchemaDirectiveWiring {

    @Override
    public GraphQLFieldDefinition onField(
            SchemaDirectiveWiringEnvironment<GraphQLFieldDefinition> environment) {

        GraphQLFieldDefinition field = environment.getElement();

        DataFetcher<?> originalDataFetcher =
                environment.getCodeRegistry().getDataFetcher(
                        environment.getFieldsContainer(), field);

        DataFetcher<?> wrappedDataFetcher =
                DataFetcherFactories.wrapDataFetcher(
                        originalDataFetcher,
                        (dataFetchingEnvironment, value) -> {
                            if (value instanceof String text) {
                                return text.toUpperCase(Locale.ROOT);
                            }
                            return value;
                        });

        environment.getCodeRegistry().dataFetcher(
                environment.getFieldsContainer(),
                field,
                wrappedDataFetcher);

        return field;
    }
}
~~~

The directive retrieves the current data fetcher from the code registry, wraps it using **DataFetcherFactories.wrapDataFetcher**, and then re-registers the wrapped data fetcher for the field. The value is transformed after the original data fetcher returns.

**Locale.ROOT** is used for locale-independent uppercasing, preventing results from depending on the server's default locale. This example assumes the directive-annotated field returns a `String`; in real applications, clearly define supported data types and avoid applying the directive to incompatible fields.

If a field has its own data fetcher provided by **@SchemaMapping** or **@QueryMapping**, wiring needs to wrap the data fetcher registered for that field. Check the runtime configuration to ensure the directive is applied after the original data fetcher has been determined.

## 6. Registering directives via RuntimeWiringConfigurer

In Spring for GraphQL, custom schema directives can be registered through a **RuntimeWiringConfigurer** bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlDirectiveConfiguration {

    @Bean
    RuntimeWiringConfigurer directiveWiringConfigurer() {
        return wiringBuilder ->
                wiringBuilder.directive(
                        "uppercase",
                        new UppercaseDirective());
    }
}
~~~

The name **uppercase** must match the directive name declared in the SDL. Spring Boot collects **RuntimeWiringConfigurer** beans and applies them when building runtime wiring for the GraphQL schema.

When the application starts:

1. Spring Boot locates SDL resources according to schema location configuration.
2. The SDL is parsed into schema definitions.
3. Spring Boot applies **RuntimeWiringConfigurer** beans, including directive wiring registrations.
4. GraphQL Java builds the executable schema and invokes **SchemaDirectiveWiring** on schema elements carrying the corresponding directive.
5. The finalized schema is used to execute operations.

If a directive is declared without registering wiring, the schema may still parse as metadata depending on engine settings, but custom behavior will not appear. Test both schema startup and execution output.

## 7. Directives with arguments

Directives can accept arguments to tailor their behavior. Example formatting directive:

~~~graphql
directive @formatDate(pattern: String! = "yyyy-MM-dd") on FIELD_DEFINITION

type Book {
  publishedAt: String @formatDate(pattern: "dd/MM/yyyy")
}
~~~

The **pattern** argument serves as configuration metadata for the field. When implementing wiring, you can read the applied directive on the schema element and extract the corresponding argument value to configure the formatter.

In GraphQL Java, APIs for reading directive arguments may differ between older directive representations and the applied directive API across versions. In real implementations, use the API appropriate for the GraphQL Java version managed by Spring Boot, preferring the current applied directive representation. Do not copy directive-argument reading snippets from another version without checking dependencies.

Determine upfront:

- Which arguments are required and which have defaults.
- Whether values must be validated when building the schema.
- Whether the directive can be repeatable.
- If an argument is invalid, whether the application should fail startup or report a runtime error.
- Whether the directive affects schema metadata or transforms values at execution time.

If a directive configures a formatter, regex, or policy, validate the configuration once when building the schema to avoid repeatedly discovering errors on every request.

## 8. Directives on objects, arguments, and input fields

Directives do not apply only to output fields. Depending on the declared locations, directives can be attached to objects, arguments, or input fields.

Example:

~~~graphql
directive @sensitive on FIELD_DEFINITION
directive @requiredInput on INPUT_FIELD_DEFINITION
directive @audit on OBJECT

type Customer @audit {
  id: ID!
  email: String! @sensitive
}

input CreateCustomerInput {
  email: String! @requiredInput
}
~~~

The directives above describe metadata about auditing, sensitivity, and input requirements. However, directive names do not automatically create auditing, data masking, or validation mechanisms. Runtime wiring or another application component must read the metadata and enforce the corresponding policy.

For directives on input fields, the **onInputObjectField** callback can be used to inspect or adjust the schema element during schema construction. However, actual input value validation typically needs to be performed via GraphQL coercion, custom scalars, Bean Validation, or application logic.

Do not treat directive metadata as an automatic security layer. If the **email** field is sensitive, the server must still enforce read permissions on that field at runtime.

## 9. Directives for authorization: intentional design

A directive can be designed to express role requirements:

~~~graphql
directive @requiresRole(role: String!) on FIELD_DEFINITION

type Query {
  adminReport: AdminReport @requiresRole(role: "ADMIN")
}
~~~

This directive makes the policy visible directly in the schema. However, to genuinely protect the field, runtime wiring must integrate with the authentication context and trusted permission checks.

One implementation approach is wrapping the data fetcher:

1. Obtain the authenticated principal or authentication from the GraphQL context.
2. Read the required role from the applied directive.
3. Check whether the principal has the appropriate permission.
4. If unauthorized, return an authorization error according to application policy.
5. If authorized, invoke the original data fetcher.

Never read roles from client-supplied arguments. Permissions must be derived from the server-authenticated principal. Moreover, a custom authorization directive does not replace Spring Security; consider method security, service-layer permission checks, and protecting all entry paths to the same business functionality.

For systems requiring complex authorization by tenant, owner, or resource, the service layer is usually the right place to enforce final rules. Directives can serve as metadata or an integration layer, but should not be the sole line of defense protecting data.

## 10. Schema directives and executable directives differ

A common misconception is assuming all directives are handled by **SchemaDirectiveWiring**. In reality:

| Kind | Example | When Processed |
|---|---|---|
| Schema directive | **@uppercase**, **@requiresRole** on field definitions | During schema construction or when runtime reads metadata |
| Executable directive | **@skip**, **@include** on fields in a query | While processing a GraphQL operation |

**SchemaDirectiveWiring** processes directives attached to schema elements. For directives attached within operations, you need an appropriate GraphQL Java execution mechanism or extension point, such as instrumentation or operation-processing logic. Do not expect **SchemaDirectiveWiring** to be invoked automatically for directives sent by clients in queries.

Example:

~~~graphql
directive @uppercase on FIELD_DEFINITION

type Book {
  title: String! @uppercase
}
~~~

This is a schema directive.

In a query:

~~~graphql
query {
  book(id: "book-01") {
    title @skip(if: false)
  }
}
~~~

**@skip** is an executable directive on a field selection. It is handled by the GraphQL engine according to standard semantics.

## 11. Directives and other mechanisms in Spring for GraphQL

Not every requirement calls for a custom directive. Choose the extension point by responsibility:

| Need | Typically Suitable Mechanism |
|---|---|
| Marking an old field | **@deprecated** |
| Skipping or including a field in an operation | **@skip**, **@include** |
| Adding metadata or behavior to a schema element | **SchemaDirectiveWiring** |
| Fetching data for a field | **@SchemaMapping**, **@QueryMapping**, `DataFetcher` |
| Resolving concrete object types for interfaces/unions | **TypeResolver** |
| Converting scalars | Custom **GraphQLScalarType** and coercing |
| Handling resolver errors | **DataFetcherExceptionResolver** or **@GraphQlExceptionHandler** |
| Measuring execution | GraphQL Java Instrumentation |
| Business authorization | Spring Security and service authorization |

Directives are suitable when behavior or metadata can be declaratively attached to schema elements. If the logic is simply querying data, use a resolver. If the logic is complex authorization, ensure the service layer still enforces policies regardless of whether a request arrives via GraphQL or another adapter.

## 12. Testing directive wiring

Tests should verify that the directive actually affects the schema or response. Checking only that the SDL contains the directive name is not enough.

For the **@uppercase** directive example, suppose the resolver returns an original title of **Spring GraphQL**. A test can verify the final value:

~~~java
@SpringBootTest
class UppercaseDirectiveTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void shouldApplyUppercaseDirective() {
        graphQlTester.document("""
                query {
                    book(id: "book-01") {
                        title
                    }
                }
                """)
            .execute()
            .path("book.title")
            .entity(String.class)
            .isEqualTo("SPRING GRAPHQL");
    }
}
~~~

Beyond testing the response, verify:

1. The application starts up when the directive is declared and wiring is registered.
2. The directive is permitted only at its declared locations.
3. Fields without the directive retain their original behavior.
4. The original data fetcher is still invoked properly and errors propagate according to GraphQL rules.
5. Null values or non-String return types are handled intentionally.
6. Directives with arguments receive the right values and defaults.
7. Repeatable directives are handled according to their designed semantics.
8. Authorization directives deny unauthorized principals and allow valid principals.
9. Directives on input fields or objects are not mistaken for automatic validation.
10. Operation directives such as **@skip** and **@include** continue working per the GraphQL specification.

If a directive is widely used, write dedicated unit tests for the **SchemaDirectiveWiring** class as well as integration tests with the real schema. This helps catch compatibility issues when upgrading GraphQL Java or Spring Boot versions.

## 13. Common mistakes when wiring directives

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Directive exists in SDL but has no effect | `SchemaDirectiveWiring` not registered | Register it via `RuntimeWiringConfigurer` |
| Directive reports invalid location error | Location list in definition omits where it is applied | Fix the location list or move the directive |
| Directive name mismatch | Name in SDL differs from name registered at runtime | Use the exact same name in both places |
| Field returns untransformed value | Wrapper was not attached to the actual data fetcher | Check the code registry and wiring order |
| Original resolver is not called | Wiring replaced the data fetcher instead of wrapping it | Retrieve and wrap the existing data fetcher |
| Authorization directive does not protect data | Metadata only, no runtime check | Enforce policies at the server and service layers |
| Using `SchemaDirectiveWiring` for `@skip`/`@include` | Confusing schema directives with executable directives | Rely on standard operation semantics |
| Invalid directive argument format | Applied directive arguments not validated | Validate during schema construction |
| Version upgrade breaks wiring code | GraphQL Java API changed | Consult the API for the managed dependency version |

## 14. Workflow for adding a custom directive

When adding a directive in Spring for GraphQL, follow these steps:

1. Determine whether the directive is metadata-only or must produce runtime behavior.
2. Choose appropriate schema locations or executable locations.
3. Declare the directive definition in the SDL, including arguments, defaults, and `repeatable` if needed.
4. Attach the directive to the appropriate types, fields, or schema elements.
5. Write **SchemaDirectiveWiring** if it is a schema directive requiring runtime behavior.
6. Register the wiring via **RuntimeWiringConfigurer**.
7. Preserve the original data fetcher and wrap it if only adding behavior.
8. Validate directive arguments when building the schema.
9. Enforce authorization and sensitive-data checks in the server/service layer.
10. Write unit/integration tests to verify actual behavior.

Directives help place metadata and certain declarative policies right alongside schema definitions. In Spring for GraphQL, SDL defines directives and locations; **SchemaDirectiveWiring** implements behavior on schema elements; **RuntimeWiringConfigurer** connects that wiring to the GraphQL runtime. When you clearly distinguish schema directives from executable directives and test behavior after wiring, directives become a useful extension point without blurring the responsibilities of resolvers, services, and Spring Security.
