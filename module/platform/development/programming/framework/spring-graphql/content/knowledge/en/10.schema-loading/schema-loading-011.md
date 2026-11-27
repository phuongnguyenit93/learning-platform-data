# Schema inspection before running

In Spring for GraphQL, the schema is the contract describing the queries, mutations, subscriptions, object types, inputs, scalars, and abstract types provided by the API. Before the application accepts requests, you should verify that the schema is completely loaded, structurally valid, and contains the components the application expects.

**Schema inspection** is checking the schema after SDL files have been discovered and combined into an executable GraphQL schema. This catches issues early such as missing types, wrong root fields, missing required fields, or unexpected contract changes. With Spring for GraphQL, you can inspect the built schema via `GraphQlSource`, enforce application-specific rules when Spring initializes the context, and use `GraphQlTester` to verify actual runtime behavior.

## 1. Why inspect the schema before running the API?

An application may have many SDL files—for example, splitting `Query`, `Mutation`, domain types, and extensions. Having files on disk does not guarantee the final schema is right.

Common issues include:

- An SDL file falls outside the configured resource pattern and is not loaded.
- A type or scalar is referenced without being defined.
- Multiple files define duplicate types or fields, or extend types with invalid syntax.
- Required root types or fields were renamed or deleted.
- Unions, interfaces, or custom scalars lack proper resolution/registration.
- The schema remains syntactically valid yet no longer matches resolvers or the contract clients rely on.

Schema inspection detects structural errors and application-specific schema conditions at startup or in tests. This is especially important in Spring for GraphQL, where SDL schemas, resolvers, directives, and runtime wiring components together form the API.

## 2. Through which steps is the schema formed?

In a typical Spring Boot setup, the schema construction process can be summarized as follows:

```text
SDL files in resources
        |
        v
Find resources via schema locations
        |
        v
Read and parse SDL
        |
        v
Combine type definitions and extensions
        |
        v
Apply RuntimeWiringConfigurer
        |
        v
Build GraphQLSchema / GraphQlSource
        |
        v
Inspect schema and application rules
        |
        v
GraphQL endpoint ready to serve requests
```

Spring Boot typically searches for schemas in `classpath:graphql/**/`, with common extensions such as `.graphqls` and `.gqls`. These locations can be customized using `spring.graphql.schema.locations`.

Example configuring multiple schema directories:

```yaml
spring:
  graphql:
    schema:
      locations:
        - classpath:graphql/common/**/
        - classpath:graphql/catalog/**/
        - classpath:graphql/order/**/
```

When declaring a custom list of locations, list all directories the application needs to load. Do not assume the default location is automatically appended to your new list.

After SDL is loaded, GraphQL Java builds `GraphQLSchema` and wires runtime wiring. Spring for GraphQL uses `GraphQlSource` as the provider of the schema and GraphQL execution object. Thus, inspecting `GraphQlSource.schema()` lets you examine the effective schema after all resources and configuration have been applied.

## 3. Distinguishing SDL checks from effective schema inspection

These two tasks are related but not identical:

| Check aspect | SDL/resource check | Effective schema inspection |
|---|---|---|
| Question | Which files exist, and is SDL syntax valid? | What types and fields exist in the final schema GraphQL will use? |
| Input | `.graphqls`, `.gqls` files and resource locations | `GraphQLSchema` after Spring/GraphQL Java builds it |
| Detects | Syntax errors, missing files, wrong patterns, extension errors | Missing root fields, missing types, wrong nullability, missing union members, or post-merge structural issues |
| Tools | Resource checks, SDL parser, startup build | `GraphQlSource.schema()`, GraphQL Java API, `SchemaPrinter`, `GraphQlTester` |

An SDL file may be valid on its own while the combined schema still has issues, such as an extension referencing a nonexistent type. Conversely, looking only at `GraphQLSchema` does not tell you which exact source file supplied each definition. When investigating schema loading issues, check both resource locations and the final schema.

## 4. Retrieving the effective schema from `GraphQlSource`

Spring for GraphQL provides `GraphQlSource`, where `schema()` returns the built `GraphQLSchema`. You can inject this bean into an inspection component:

```java
import graphql.schema.GraphQLObjectType;
import graphql.schema.GraphQLSchema;
import graphql.schema.GraphQLType;
import org.springframework.graphql.GraphQlSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.InitializingBean;

@Configuration
class GraphQlSchemaInspectionConfiguration {

    @Bean
    InitializingBean inspectGraphQlSchema(GraphQlSource graphQlSource) {
        return () -> {
            GraphQLSchema schema = graphQlSource.schema();

            GraphQLObjectType queryType = schema.getQueryType();
            if (queryType == null) {
                throw new IllegalStateException("GraphQL Query root type is missing");
            }

            GraphQLType book = schema.getType("Book");
            if (!(book instanceof GraphQLObjectType)) {
                throw new IllegalStateException("Expected GraphQL object type Book");
            }

            GraphQLObjectType bookType = (GraphQLObjectType) book;
            if (bookType.getFieldDefinition("id") == null) {
                throw new IllegalStateException("Required field Book.id is missing");
            }
        };
    }
}
```

This example checks three application conditions: a query root exists, the `Book` object type exists, and `Book` has an `id` field. If any condition fails, bean initialization fails and Spring does not complete application context startup.

These are checks tailored to your application's contract. Another API might check `Product`, `Order`, `Mutation.createOrder`, or a specific union member. Only enforce conditions the application genuinely requires; avoid hardcoding every type as mandatory if some are optional per profile.

Imports are shown to illustrate the relevant APIs. Exact APIs and imports should be verified against the Spring for GraphQL/GraphQL Java version your project uses.

## 5. Inspecting root types, fields, and return types

`GraphQLSchema` provides access to the root types:

```java
GraphQLObjectType queryType = schema.getQueryType();
GraphQLObjectType mutationType = schema.getMutationType();
GraphQLObjectType subscriptionType = schema.getSubscriptionType();
```

`queryType` is the required root type of the schema. `mutationType` and `subscriptionType` may be `null` if the API does not declare those operations.

To inspect the fields of the root query:

```java
queryType.getFieldDefinitions().forEach(field -> {
    System.out.println("Query field: " + field.getName());
});
```

You can check a specific field:

```java
if (queryType.getFieldDefinition("bookById") == null) {
    throw new IllegalStateException("Query.bookById is missing");
}
```

For an object type, you can inspect field names, arguments, and return types. For example:

```java
GraphQLObjectType bookType = (GraphQLObjectType) schema.getType("Book");
GraphQLFieldDefinition titleField = bookType.getFieldDefinition("title");

if (titleField == null) {
    throw new IllegalStateException("Book.title is missing");
}

System.out.println("Book.title type: " + titleField.getType());
```

In practice, check both type and nullability if clients depend on that guarantee. For instance, changing `String` to `String!` or vice versa can affect how clients handle data and errors. When you need to compare wrapper structures generically, traverse `GraphQLType` and distinguish `GraphQLNonNull`, `GraphQLList`, and named types.

## 6. Validating the GraphQL schema

GraphQL Java builds the schema from type definitions and runtime wiring. Beyond SDL parsing and build errors, an application can explicitly invoke `SchemaValidator` to run structural schema validation:

```java
import graphql.schema.GraphQLSchema;
import graphql.schema.validation.SchemaValidationError;
import graphql.schema.validation.SchemaValidator;

import java.util.Set;

GraphQLSchema schema = graphQlSource.schema();
Set<SchemaValidationError> errors = new SchemaValidator().validateSchema(schema);

if (!errors.isEmpty()) {
    throw new IllegalStateException("GraphQL schema validation failed: " + errors);
}
```

`SchemaValidator` adds an explicit verification step during startup or testing. Depending on the GraphQL Java version, error types and API details may vary; use the version managed by Spring Boot and check the corresponding documentation.

Schema validation does not replace business logic testing. A schema can be valid while a resolver still queries the wrong data, returns `null` for a Non-null field, or enforces authorization improperly.

## 7. Printing the effective schema for review

When you need to view the final schema after SDL files have been combined, GraphQL Java provides `SchemaPrinter`:

```java
import graphql.schema.idl.SchemaPrinter;

String effectiveSdl = new SchemaPrinter().print(graphQlSource.schema());
System.out.println(effectiveSdl);
```

The output is the SDL printed from the built schema. It is useful for reviews, saving pipeline artifacts, or diffing across releases. The printed schema may be normalized in ordering and formatting, so it will not necessarily match source files verbatim.

In a real application, use a logger or a dedicated build/test step instead of `System.out.println`. Avoid printing the entire schema into production logs if the schema contains internal descriptions or metadata that should not be exposed.

## 8. Inspecting runtime wiring and resolvers

The schema describes which fields can be called, while runtime wiring connects fields to data fetchers, scalars, type resolvers, and other execution components.

Spring for GraphQL supports multiple ways to register resolvers:

- Annotated controllers such as `@QueryMapping`, `@MutationMapping`, `@SchemaMapping`.
- `RuntimeWiringConfigurer` to register data fetchers, scalars, type resolvers, or directive wiring.
- Default property fetcher to read properties from the source object when no custom resolver exists.

Therefore, you cannot conclude a field lacks a resolver merely by inspecting the schema's field list. A field may work via the default property fetcher. Conversely, a schema may be valid while a custom scalar or union is improperly registered and only reveals the problem at execution time.

Verify critical fields with real queries in a test context. Test cases where resolvers return data, return empty/missing data, throw business errors, and return runtime types for interfaces/unions. For fields requiring authorization, test both permitted and unauthorized users.

## 9. Testing the schema with `GraphQlTester`

`GraphQlTester` lets you send GraphQL documents to the schema inside a test context. You can use it to confirm fields exposed by the schema actually work:

```java
@GraphQlTest(BookController.class)
class BookSchemaTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @Test
    void bookQueryIsAvailable() {
        given(bookService.findById("book-01"))
            .willReturn(new Book("book-01", "GraphQL Basics"));

        graphQlTester.document("""
                query {
                    bookById(id: "book-01") {
                        id
                        title
                    }
                }
                """)
            .execute()
            .path("bookById.id").entity(String.class).isEqualTo("book-01");
    }
}
```

This is an illustrative example; imports, the static import for `given`, and SDL declaring `Query.bookById` and `Book` must be present in the test context. Depending on the Spring Boot version, the mock bean annotation may be `@MockitoBean` or `@MockBean`. You can add assertions for `title`, test missing fields, or test errors when a resolver returns data violating declared nullability.

Introspection tests can also verify type and field names, while business queries like the example above verify both the schema and the resolver execution path. Both approaches complement each other: introspection verifies metadata; real queries verify behavior.

## 10. Integrating schema inspection into startup and CI

A practical verification workflow can include:

1. **Resource check:** confirm the schema locations pattern discovers the expected SDL files.
2. **Build application context:** let Spring Boot and GraphQL Java parse, combine SDL, and create `GraphQlSource`.
3. **Effective schema inspection:** confirm root types, key types, required fields, nullability, and interface/union members.
4. **Runtime wiring check:** verify custom scalars, type resolvers, directive wiring, and key resolvers.
5. **Run GraphQlTester:** send operations representative of the API and assert responses.
6. **Schema comparison:** if needed, print the effective schema using `SchemaPrinter` or use introspection to diff against the previous release.

You can place these checks in a test suite or in an inspection bean during application context initialization. If a startup check fails, let initialization fail clearly instead of continuing to serve a schema that violates the contract the application requires.

An `InitializingBean` is created after its `GraphQlSource` dependency is ready, so it can inspect the schema during context initialization. With checks run via `ApplicationRunner`, code executes after the context initializes and before Spring Boot publishes `ApplicationReadyEvent`; coordinate with readiness probes if deploying in an environment with load balancers or orchestration.

## 11. Common mistakes during inspection

**Checking only SDL files without inspecting the final schema.** Resources might not be loaded due to a wrong pattern or profile. Check `GraphQlSource.schema()` after the application builds the schema.

**Assuming a valid schema means resolvers work.** Schema validation mainly checks structure. Send queries via `GraphQlTester` to verify resolvers and runtime wiring.

**Requiring every field to have a dedicated resolver.** Many fields are resolved by the default property fetcher. Only check for custom resolvers where the application genuinely requires custom logic.

**Skipping nullability checks.** Changing a field from nullable to Non-null or vice versa can alter client behavior. Treat nullability as part of the API contract.

**Ignoring unions and interfaces.** Abstract types require accurate runtime type resolution. Check `possibleTypes` and test each concrete member.

**Logging the schema without asserting conditions.** Printing SDL aids visibility, but does not automatically catch deleted required fields. Write explicit assertions for the application contract.

**Ignoring deployment environments.** Different profiles or configurations may load different schemas. Run checks under each critical environment configuration.

## Conclusion

Schema inspection before running confirms that the effective GraphQL schema has been loaded and satisfies the conditions your application requires. With Spring for GraphQL, you can retrieve the schema from `GraphQlSource`, inspect root types and fields via the GraphQL Java API, use `SchemaValidator` and `SchemaPrinter` when appropriate, and verify resolvers with `GraphQlTester`. Combining structural inspection with operation tests catches schema loading and runtime wiring errors early at startup or in CI.
