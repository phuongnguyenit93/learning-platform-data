# Custom Schema Directive

A GraphQL schema describes data types, fields, and the operations clients can invoke. In many applications, merely describing data types is not enough: a field may require access permissions, caching rules, sensitive-data markers, or value transformation before being returned. A **directive** is GraphQL's extension syntax for attaching metadata or behavior to a schema and operations. Custom schema directives let an application define its own rules directly in SDL.

In Spring for GraphQL, schema directives can be processed when building the GraphQL runtime using GraphQL Java's SchemaDirectiveWiring. Spring Boot picks up the configuration through a RuntimeWiringConfigurer bean, allowing the directive to intercept the corresponding field definition or data fetcher.

## What Is a Directive?

A directive is an instruction starting with the `@` character, followed by the directive name and optional arguments. For example, GraphQL predefines the @deprecated directive to mark fields or enum values as no longer recommended:

~~~graphql
type Book {
  id: ID!
  title: String!
  oldTitle: String @deprecated(reason: "Use title instead")
}
~~~

The @deprecated directive provides metadata for the schema and developer tools. GraphQL clients can inspect this information via introspection to display warnings when using older fields.

Other built-in directives include:

| Directive | Purpose | Typical Locations |
| --- | --- | --- |
| **@skip(if: Boolean!)** | Skips a field or fragment when the condition is true | Query, field, fragment |
| **@include(if: Boolean!)** | Includes a field or fragment only when the condition is true | Query, field, fragment |
| **@deprecated(reason: String)** | Marks a field or enum value as deprecated | Schema definition |
| **@specifiedBy(url: String!)** | Publishes the format specification for a custom scalar | Scalar definition |

@skip and @include are typically placed by clients in operations to control selection sets via variables. @deprecated and @specifiedBy are attached to schema definitions. Custom schema directives are likewise declared and applied to schema elements such as objects, fields, arguments, enums, or scalars.

## Defining a Custom Directive in SDL

Use the `directive` keyword to define a directive. The basic syntax consists of a name, an optional argument list, and the allowed locations following the `on` keyword:

~~~graphql
directive @auth(role: String!) on FIELD_DEFINITION
~~~

The definition above creates the @auth directive with one required argument `role`, allowed only on field definitions. For example:

~~~graphql
type Query {
  publicMessage: String!
  adminReport: String! @auth(role: "ADMIN")
}
~~~

Here, @auth attaches metadata to the adminReport field. Merely declaring the directive in SDL does not automatically check user permissions. The application must register handling for the directive or protect the resolver with an appropriate security mechanism. Without server-side implementation, the directive is only schema metadata.

Directives can have arguments with default values:

~~~graphql
enum AccessRole {
  USER
  ADMIN
}

directive @requiresRole(
  role: AccessRole! = USER
) on FIELD_DEFINITION

type Query {
  profile: Profile @requiresRole
  auditLog: [AuditEntry!]! @requiresRole(role: ADMIN)
}
~~~

profile uses the default value USER; auditLog requires ADMIN. Using an enum instead of a free-form string helps the schema constrain valid values and describe the contract more clearly.

## Directive Locations

Directive locations specify where a directive is allowed to appear. Applying a directive in an invalid location makes the schema invalid. Common locations in the type system group include:

| Location | Target Element |
| --- | --- |
| **SCHEMA** | Entire schema |
| **SCALAR** | Scalar type |
| **OBJECT** | Object type |
| **FIELD_DEFINITION** | Field declared inside a type |
| **ARGUMENT_DEFINITION** | Argument of a field or directive |
| **INTERFACE** | Interface type |
| **UNION** | Union type |
| **ENUM** | Enum type |
| **ENUM_VALUE** | An enum value |
| **INPUT_OBJECT** | Input object type |
| **INPUT_FIELD_DEFINITION** | Field inside an input object |

For example, a directive marking data that needs masking in responses might only be allowed on fields:

~~~graphql
directive @sensitive on FIELD_DEFINITION

type User {
  id: ID!
  displayName: String!
  email: String! @sensitive
}
~~~

If a directive needs to apply to both objects and fields, declare multiple locations:

~~~graphql
directive @audit(event: String!) on OBJECT | FIELD_DEFINITION
~~~

OBJECT | FIELD_DEFINITION means the directive can be attached to an object type or a specific field. The location list is part of the directive's contract, not a suggestion list.

## Repeatable Directives

By default, a directive cannot be repeated multiple times at the same location. When multiple values need to be attached, declare the `repeatable` keyword:

~~~graphql
directive @tag(name: String!) repeatable on OBJECT | FIELD_DEFINITION

type Book
  @tag(name: "catalog")
  @tag(name: "searchable") {
  id: ID!
  title: String! @tag(name: "display")
}
~~~

In this example, the Book object receives two tags. Without `repeatable`, placing the same @tag directive multiple times on Book would violate schema rules. Repeatable directives fit metadata that can have multiple values such as tags, categories, or classification labels.

A directive can be defined with multiple arguments:

~~~graphql
enum CacheScope {
  PUBLIC
  PRIVATE
}

directive @cacheControl(
  maxAge: Int! = 60
  scope: CacheScope! = PUBLIC
) on OBJECT | FIELD_DEFINITION

type Query {
  publicCatalog: [Book!]!
    @cacheControl(maxAge: 300, scope: PUBLIC)
  myProfile: Profile!
    @cacheControl(maxAge: 0, scope: PRIVATE)
}
~~~

The @cacheControl directive in the example represents cache metadata. The server or gateway must read the metadata and apply the corresponding caching policy; GraphQL does not change HTTP caching automatically just because SDL contains this directive.

## Schema Directives vs. Executable Directives

GraphQL allows placing directives in two location groups:

- **Schema/type-system directives** are attached to schema definitions such as OBJECT, FIELD_DEFINITION, SCALAR, or ENUM_VALUE. They are typically processed during schema construction and runtime wiring.
- **Executable directives** are placed in client operations such as QUERY, FIELD, FRAGMENT_SPREAD, or INLINE_FRAGMENT. They affect how an operation is validated or executed.

Example of a schema directive:

~~~graphql
type User {
  email: String! @sensitive
}
~~~

Example of an executable directive:

~~~graphql
query UserDetails($includeEmail: Boolean!) {
  user(id: "user-10") {
    id
    displayName
    email @include(if: $includeEmail)
  }
}
~~~

Both kinds of directives share the `@` syntax, but they are processed at different stages. SchemaDirectiveWiring in GraphQL Java is meant for wiring directives on schema elements. If you want to define a custom directive in client operations, you need an execution-layer mechanism such as instrumentation or an appropriate extension; registering a SchemaDirectiveWiring does not make an executable directive run.

## Implementing a Custom Schema Directive with GraphQL Java

The following example creates an @uppercase directive to convert a field's returned string to uppercase. It illustrates how a directive wraps an existing data fetcher:

~~~graphql
directive @uppercase on FIELD_DEFINITION

type Query {
  greeting: String! @uppercase
}
~~~

Implementing SchemaDirectiveWiring:

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

        DataFetcher<?> originalFetcher =
                environment.getCodeRegistry().getDataFetcher(
                        environment.getFieldsContainer(), field);

        DataFetcher<?> wrappedFetcher = DataFetcherFactories.wrapDataFetcher(
                originalFetcher,
                (dataFetchingEnvironment, value) -> {
                    if (value instanceof String text) {
                        return text.toUpperCase(Locale.ROOT);
                    }
                    return value;
                });

        environment.getCodeRegistry().dataFetcher(
                environment.getFieldsContainer(), field, wrappedFetcher);

        return field;
    }
}
~~~

onField is called when GraphQL Java processes a directive attached to a field definition. The implementation fetches the current data fetcher, wraps it with a result-transforming function, and registers the new data fetcher in the code registry. Thus, the original resolver logic still executes; the directive only transforms the value after the resolver returns.

Locale.ROOT is used to uppercase strings consistently, independent of the server's locale. This example only converts String values; other types are returned as is.

## Registering Directives in Spring for GraphQL

Spring for GraphQL lets you add schema wiring via a RuntimeWiringConfigurer bean. Register the uppercase directive as follows:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;

@Configuration
public class GraphQlDirectiveConfiguration {

    @Bean
    RuntimeWiringConfigurer directiveWiringConfigurer() {
        return builder -> builder.directive(
                "uppercase",
                new UppercaseDirective()
        );
    }
}
~~~

Spring Boot detects this bean when building the GraphQL runtime. The name passed to builder.directive must match the directive name declared in SDL. When the schema has a field annotated with @uppercase, GraphQL Java invokes UppercaseDirective during wiring.

The resolver can return a normal string:

~~~java
@Controller
public class GreetingController {

    @QueryMapping
    public String greeting() {
        return "hello from spring graphql";
    }
}
~~~

When the client sends:

~~~graphql
query {
  greeting
}
~~~

The response received is:

~~~json
{
  "data": {
    "greeting": "HELLO FROM SPRING GRAPHQL"
  }
}
~~~

The uppercase rule lives in the directive wiring, not in the controller. This organization is useful for genuinely shared presentation behaviors or metadata. For critical business logic, consider placing it in a service or resolver so behavior is easier to test and observe.

## Using Directives for Security Metadata

A directive can express access requirements directly in the schema:

~~~graphql
enum Role {
  USER
  ADMIN
}

directive @requiresRole(role: Role!) on FIELD_DEFINITION

type Query {
  profile: Profile! @requiresRole(role: USER)
  auditLog: [AuditEntry!]! @requiresRole(role: ADMIN)
}
~~~

This definition helps schema readers recognize which fields require a role. However, @requiresRole does not authenticate users or block requests on its own. The server must implement enforcement. In a Spring application, resolvers can be protected with Spring Security method security:

~~~java
@Controller
public class AdminController {

    @PreAuthorize("hasRole('ADMIN')")
    @QueryMapping
    public List<AuditEntry> auditLog() {
        return auditService.findRecentEntries();
    }
}
~~~

This example requires enabling method security in the Spring Security configuration. A directive can serve as metadata for tooling, documentation, or custom wiring, but access permissions must be enforced on the server based on the current principal. Do not merely hide a field or rely on clients not sending a field as a security measure.

## Testing Custom Schema Directives

Test both the wiring and operation results:

| Case | Expected Result |
| --- | --- |
| Field with @uppercase returns String | Response value is converted to uppercase |
| Resolver returns a non-String type | Value remains unchanged per the example implementation |
| Field without @uppercase | Result is not transformed |
| Directive placed at wrong location | Schema fails to build |
| SDL has directive but no wiring registered | Server reports a wiring error or directive has no behavior depending on schema setup |
| Field with role requirement | Authorized users are allowed; unauthorized users are denied |

You can use GraphQlTester to verify the result:

~~~java
graphQlTester.document("""
        query {
            greeting
        }
        """)
    .execute()
    .path("greeting")
    .entity(String.class)
    .isEqualTo("HELLO FROM SPRING GRAPHQL");
~~~

For directives with arguments, test both default values and explicitly passed values. For repeatable directives, verify how wiring handles multiple occurrences and ordering if behavior depends on order. For security directives, include tests for both permitted and denied cases.

## Introspection and Directive Discoverability

GraphQL introspection allows clients or developer tools to discover directives published by the schema, including name, description, locations, arguments, and repeatable status if supported by the runtime version. For example:

~~~graphql
query Directives {
  __schema {
    directives {
      name
      description
      isRepeatable
      locations
      args {
        name
        description
      }
    }
  }
}
~~~

Introspection helps IDEs or API documentation display how a directive is defined. It does not prove the directive is implemented properly or that its policy is enforced. To confirm behavior, test actual operations and runtime configuration.

## Design Principles for Custom Schema Directives

When creating custom directives, follow these principles:

1. **Choose precise locations.** Only allow the directive where it makes sense, avoiding schema clutter.
2. **Use clear names and descriptions.** Directive names should convey purpose, and arguments should have sensible types and defaults.
3. **Separate metadata from enforcement.** Declaring a directive does not mean behavior is implemented; there must be corresponding wiring or an enforcement layer.
4. **Keep logic shared and well-scoped.** Directives fit cross-cutting behavior across many fields, but should not become a home for complex business logic.
5. **Wrap data fetchers carefully.** Preserve errors, context, instrumentation, and asynchronous behavior of the original fetcher; do not block reactive streams.
6. **Do not treat directives as the sole security boundary.** Authentication and authorization must be enforced on the server using Spring Security or an equivalent mechanism.
7. **Test both schema and runtime.** Verify directive locations, arguments, wiring, outputs, and errors.

Custom schema directives extend SDL's expressiveness by attaching shared metadata or behavior to schema elements. In Spring for GraphQL, SDL defines the directive and where it is permitted, GraphQL Java processes it through SchemaDirectiveWiring, and RuntimeWiringConfigurer registers the wiring mechanism with the runtime. Understanding the boundary between declaration and execution turns directives into a controlled part of the API contract.
