# Protecting introspection

GraphQL includes an introspection mechanism that allows clients to query the server about the deployed schema: root query/mutation/subscription types, object types, fields, arguments, scalars, enums, directives, descriptions, and deprecation status. This makes GraphQL self-describing and powers tools like GraphiQL, but can also expose internal API structure if every client is permitted to query the schema.

Spring Boot enables field introspection by default. Spring for GraphQL lets you disable introspection at the schema level using `spring.graphql.schema.introspection.enabled=false`. GraphQL Java also supports per-request policies via `Introspection.INTROSPECTION_DISABLED` in `GraphQLContext`. As a result, applications can disable introspection entirely in production or allow only users with an appropriate role to inspect the schema.

This lesson explains how introspection works, how to disable it via Spring Boot configuration, how to apply per-request policies, how to test it, and what limitations to understand before treating this as a hardening measure.

## 1. What is introspection?

Introspection is GraphQL's capability allowing clients to query metadata about the schema itself. The two main meta-fields are:

- `__schema`: returns overall information about the schema.
- `__type(name: String!)`: returns information about a type with a specific name.

Example querying root types:

```graphql
query InspectSchema {
  __schema {
    queryType {
      name
    }
    mutationType {
      name
    }
    subscriptionType {
      name
    }
  }
}
```

Example inspecting fields of a type:

```graphql
query InspectBook {
  __type(name: "Book") {
    name
    kind
    description
    fields {
      name
      description
      isDeprecated
      deprecationReason
      type {
        kind
        name
      }
    }
  }
}
```

Clients can use introspection to:

- Discover operations and fields offered by the API.
- Find valid input types, arguments, scalars, and enums.
- Generate documentation and client code.
- Support autocomplete, validation, and schema explorers in IDEs.
- Detect deprecated fields along with deprecation reasons.

A GraphQL schema is therefore not only a contract between client and server; when introspection is enabled, the server also exposes a machine-readable interface to explore that contract.

## 2. Distinguishing `__schema`, `__type`, and `__typename`

Not every field starting with two underscores serves the same purpose:

| Meta-field | Purpose | When introspection is disabled |
| --- | --- | --- |
| `__schema` | Explore the entire schema | Blocked |
| `__type` | Explore a single type by name | Blocked |
| `__typename` | Retrieve the runtime type name of the current object | Still works |

`__typename` is very useful when clients work with interfaces, unions, or normalized caches. It tells the client which concrete type an object has in the response:

```graphql
query BookDetails {
  bookById(id: "book-1") {
    __typename
    id
    title
  }
}
```

Example response:

```json
{
  "data": {
    "bookById": {
      "__typename": "Book",
      "id": "book-1",
      "title": "Spring for GraphQL"
    }
  }
}
```

In GraphQL Java, the introspection disabling mechanism checks the `__schema` and `__type` meta-fields; `__typename` is not a schema discovery query and is retained. Do not block all fields prefixed with `__` using a blanket field visibility rule if the application still needs `__typename`.

## 3. Why protect introspection?

When introspection is open to everyone, clients can discover:

- Type and field names exposed by the API.
- Mutations and input objects.
- Deprecated fields or arguments.
- Schema descriptions and nullability rules.
- Parts of the API intended for internal integrations.

This information helps legitimate testers and API consumers, but also helps attackers understand the API surface faster. For example, administrative mutation names, fields holding sensitive data, or internal business flows can become easy to spot.

However, introspection is not data access authorization. Disabling introspection does not stop a client from calling a field whose name they already know. If a resolver lacks authorization, the client can still call that field directly. Conversely, an API well-protected at the field level can still allow introspection without exposing business data.

Treat disabling introspection as an additional hardening layer, combined with:

- Authentication at the transport or API gateway.
- Authorization at field resolvers, services, and domain boundaries.
- Limits on query depth, complexity, operation count, and execution time.
- Rate limiting, logging, and monitoring.
- Error messages that do not leak stack traces or internal details.

Never rely on hiding the schema as your sole security measure.

## 4. Disabling introspection with Spring Boot

Spring Boot provides the property:

```yaml
spring:
  graphql:
    schema:
      introspection:
        enabled: false
```

By default, `spring.graphql.schema.introspection.enabled` is `true`. Set it to `false` to disable field introspection when Boot builds the GraphQL source.

You can split configuration by profile:

```yaml
# application-dev.yml
spring:
  graphql:
    schema:
      introspection:
        enabled: true
```

```yaml
# application-prod.yml
spring:
  graphql:
    schema:
      introspection:
        enabled: false
```

In development, introspection helps GraphiQL and IDEs explore the schema. In production, whether to enable or disable it depends on the API model and client needs. If a public API needs to support code generation or a developer portal, you can keep introspection available to an authenticated consumer group rather than disabling it completely.

### Configuration in application.properties

```properties
spring.graphql.schema.introspection.enabled=false
```

This property controls introspection at the GraphQL Java schema/runtime level. It does not remove the schema from the application, does not alter SDL, and does not automatically add authorization to fields.

## 5. Disabling introspection per request using GraphQLContext

In some cases, only certain clients or roles should be allowed to explore the schema:

- Developers or schema readers are allowed to run introspection.
- Regular users are not allowed to run introspection.
- Internal APIs and public APIs can apply different policies.

GraphQL Java provides the `Introspection.INTROSPECTION_DISABLED` key. Set its value to `true` in a request's `GraphQLContext` to reject introspection for that request:

```java
import graphql.introspection.Introspection;

request.configureExecutionInput((executionInput, builder) ->
        builder.graphQLContext(context ->
                context.put(Introspection.INTROSPECTION_DISABLED, true))
                .build());
```

The snippet above shows how to add the flag to the execution context. In a Spring for GraphQL application, this can be done from a `WebGraphQlInterceptor` after determining the caller's identity and permissions.

### Example WebGraphQlInterceptor with Spring Security WebFlux

The following example allows only users with the `ROLE_SCHEMA_READER` authority to perform introspection:

```java
import graphql.introspection.Introspection;
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class IntrospectionAccessInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(authentication -> authentication.getAuthorities().stream()
                        .anyMatch(authority ->
                                authority.getAuthority().equals("ROLE_SCHEMA_READER")))
                .defaultIfEmpty(false)
                .flatMap(allowed -> {
                    request.configureExecutionInput((executionInput, builder) ->
                            builder.graphQLContext(context ->
                                    context.put(
                                            Introspection.INTROSPECTION_DISABLED,
                                            !allowed))
                                    .build());
                    return chain.next(request);
                });
    }
}
```

Key points:

1. Permissions are read from the Spring Security reactive context, not from an arbitrary client-sent header.
2. If there is no authentication or the required authority is missing, `allowed` is `false`.
3. `INTROSPECTION_DISABLED` receives the negation of `allowed`.
4. The flag is placed in the `GraphQLContext` of that specific execution, so other requests do not share this decision.

This example assumes the application has configured Spring Security WebFlux and authenticated the principal before the interceptor. For Spring MVC, how SecurityContext is obtained differs from WebFlux, though it must still come from the context authenticated by Spring Security.

### Precedence between JVM-wide configuration and per-request flag

GraphQL Java has two control levels:

| Level | API | Scope |
| --- | --- | --- |
| JVM-wide | `Introspection.enabledJvmWide(false)` | Disables introspection for all GraphQL executions in the same JVM |
| Per-request | `Introspection.INTROSPECTION_DISABLED = true` | Disables introspection for a single execution |

These two levels combine monotonically (can only restrict further):

- If introspection is disabled JVM-wide, a request cannot re-enable it via context.
- If introspection is enabled JVM-wide, a request can disable it for itself via `INTROSPECTION_DISABLED=true`.
- If the key is absent or `false`, the request uses the JVM-wide state.

Spring Boot's `spring.graphql.schema.introspection.enabled=false` uses GraphQL Java's global disable mechanism. Therefore, if you need role-based introspection, do not set the JVM-wide flag to `false`; leave the global state enabled and apply decisions per request.

## 6. Controlling GraphiQL and schema printer separately

Disabling field introspection does not automatically disable all schema-discovery endpoints. Spring Boot provides developer-experience endpoints:

| Component | Property | Default |
| --- | --- | --- |
| GraphiQL UI | `spring.graphql.graphiql.enabled` | Disabled |
| Schema printer | `spring.graphql.schema.printer.enabled` | Disabled |
| Field introspection | `spring.graphql.schema.introspection.enabled` | Enabled |

GraphiQL is a web UI for sending GraphQL operations, served at `/graphiql` by default when enabled. It usually needs introspection to load the schema and provide autocomplete. The schema printer can return the schema as SDL at `/graphql/schema` when enabled.

In production, if these tools are not needed, configure them explicitly:

```yaml
spring:
  graphql:
    graphiql:
      enabled: false
    schema:
      printer:
        enabled: false
      introspection:
        enabled: false
```

GraphiQL might be enabled in development via configuration or DevTools. Verify the production profile and live endpoints after deployment; do not assume disabling introspection also removes the GraphiQL page or schema printer.

If a developer portal is needed, place it in an environment or separately authenticated endpoint, and grant access only to the group that needs it.

## 7. Notes when configuring a custom GraphQlSource

Spring Boot's introspection property is applied during auto-configuration when building `GraphQlSource`. If the application defines its own `GraphQlSource` bean, auto-configuration may back off and skip the corresponding introspection setup in some versions.

Therefore, when using a custom `GraphQlSource`:

1. Do not rely solely on the property appearing in `application.yml`.
2. Check the actual configuration behavior of your exact Spring Boot version.
3. Send an introspection query in an integration test to confirm it is rejected.
4. If needed, apply the appropriate GraphQL Java mechanism in your custom configuration and keep that policy consistent across all GraphQL executions.

This is essential to verify after customizing auto-configuration; avoid having configuration claim introspection is disabled while runtime still permits it.

## 8. Avoiding legacy ways to disable introspection

Some older examples use:

```java
NoIntrospectionGraphqlFieldVisibility.NO_INTROSPECTION_FIELD_VISIBILITY
```

or attach `NoIntrospectionGraphqlFieldVisibility` to `GraphQLSchema.Builder.fieldVisibility(...)`.

Do not use this approach in new code. `NoIntrospectionGraphqlFieldVisibility` was deprecated in GraphQL Java 22; GraphQL Java provides `Introspection.enabledJvmWide(false)` and the per-request `Introspection.INTROSPECTION_DISABLED` key to directly control introspection execution.

Generic field visibility rules can also block meta-fields clients need for normal operation, such as `__typename`, or behave differently from the current introspection guard mechanism. When upgrading GraphQL Java, check the Javadoc for your exact version rather than copying old snippets.

## 9. Disabled introspection does not mean the schema is fully protected

When `__schema` and `__type` are blocked, clients cannot use those two meta-fields to discover the schema. However, other ways to infer the API surface still remain:

- Directly sending field names the client already knows or guesses.
- Observing error messages and similar-field-name suggestions.
- Reading SDL documentation published elsewhere.
- Using client schemas, code generation artifacts, or archived API documentation.
- Discovering secondary endpoints exposed by the application or API gateway.

If you do not want to leak field names via error suggestions, examine how GraphQL Java and your application's exception handling produce validation errors. Whether field suggestions can be disabled depends on the GraphQL Java version and validation configuration; do not assume disabling introspection automatically disables suggestions.

Never place secrets, credentials, internal URLs, or sensitive data in schema descriptions. Schema descriptions can be returned via introspection or the schema printer in environments where access is allowed.

### Good faith introspection

Some versions of GraphQL Java include `GoodFaithIntrospection` to restrict the shape and size of introspection queries, such as limiting depth or field count. This mechanism aims to curb oversized or abusive introspection queries; it is not equivalent to disabling introspection and does not replace authorization.

If used, check the Javadoc for your exact GraphQL Java version to see defaults and supported limits.

## 10. Testing the introspection policy

Do not check only the property in a configuration file. Send queries to a real GraphQL execution to verify `__schema` and `__type` are rejected while business fields and `__typename` continue to work.

Example with `GraphQlTester`:

```java
@GraphQlTest(BookQueryController.class)
@TestPropertySource(properties = {
        "spring.graphql.schema.introspection.enabled=false"
})
class IntrospectionSecurityTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void rejectsSchemaIntrospection() {
        graphQlTester.document("""
                query {
                    __schema {
                        queryType {
                            name
                        }
                    }
                }
                """)
                .execute()
                .errors()
                .satisfy(errors -> assertThat(errors).isNotEmpty());
    }

    @Test
    void rejectsTypeIntrospection() {
        graphQlTester.document("""
                query {
                    __type(name: "Book") {
                        name
                        fields {
                            name
                        }
                    }
                }
                """)
                .execute()
                .errors()
                .satisfy(errors -> assertThat(errors).isNotEmpty());
    }

    @Test
    void keepsTypenameAvailable() {
        graphQlTester.document("""
                query {
                    bookById(id: "book-1") {
                        __typename
                    }
                }
                """)
                .execute()
                .errors()
                .verify()
                .path("bookById.__typename")
                .entity(String.class)
                .isEqualTo("Book");
    }
}
```

The example assumes the schema has `Query.bookById`, `book-1` data exists, and the field returns type `Book`. Add the appropriate resolvers/configuration to the test context. If you only want to test schema introspection, you can use a simple query that does not depend on business data.

`@GraphQlTest` auto-configures `GraphQlTester` to test GraphQL execution without an HTTP server. If you want to test the HTTP endpoint, GraphiQL, or headers/security filters, use `@SpringBootTest` combined with `@AutoConfigureHttpGraphQlTester` and `HttpGraphQlTester`. The `spring.graphql.graphiql.enabled` and `spring.graphql.schema.printer.enabled` properties should also be verified via integration/smoke tests against the real transport.

### Testing a role-based policy

For a role-based interceptor:

- Send `__schema` with a user holding `ROLE_SCHEMA_READER`; the query must succeed.
- Send the same query with a user lacking that role; the query must return a GraphQL error.
- Send normal queries with both users; results must obey field authorization, independent of the introspection policy.
- Send an unauthenticated request; introspection must be disabled.

This tests both the allowed branch and the default-deny branch. If you only test unauthorized users, the interceptor might accidentally disable introspection for everyone without being noticed.

### Checking secondary endpoints

In integration tests or deployment smoke tests, verify:

- `/graphiql` is not served if the UI is disabled.
- `/graphql/schema` is not served if the schema printer is disabled.
- The HTTP GraphQL endpoint still works for allowed queries/mutations.
- WebSocket or other transports do not inadvertently apply a different introspection policy than HTTP.

Note: `Introspection.enabledJvmWide(false)` is JVM-level static state. Testing multiple Spring contexts in the same JVM with different introspection settings can interfere with one another. Avoid toggling the global flag across parallel tests; prefer a fixed setting for the test suite or per-request testing via `GraphQLContext`.

## 11. Common issues

| Symptom | Cause | Solution |
| --- | --- | --- |
| Property set to false yet introspection still runs | Custom `GraphQlSource` causes auto-configuration not to apply the setting in some versions | Test runtime via integration test and configure the custom source |
| Developer with the role still cannot introspect | Global JVM flag was disabled | Do not use global disable if role-based access is needed |
| `__typename` also errors | Legacy field visibility rule blocks all `__`-prefixed fields | Use GraphQL Java `Introspection` guard instead of a blanket rule |
| GraphiQL can still be opened | Only field introspection was disabled, not the GraphiQL endpoint | Set `spring.graphql.graphiql.enabled=false` |
| Schema can still be downloaded via another URL | Schema printer or secondary endpoint is still enabled | Disable schema printer and check all transports |
| Introspection disabled yet sensitive fields still accessible | Confusing introspection with authorization | Add field/service authorization |
| Errors still suggest field names | Validation errors can emit field suggestions | Check error policy and GraphQL Java version |
| Tests pass in isolation but fail in full suite | JVM-wide static flag mutated by another test | Isolate tests or use the per-request context flag |
| Some clients fail to build schema caches | Clients rely on introspection to load the schema | Grant permission to schema readers or distribute SDL safely |

## 12. Design principles for introspection policies

- Explicitly decide whether the API needs introspection for a developer portal, code generation, and client tooling.
- Use `spring.graphql.schema.introspection.enabled=false` when disabling at the application/JVM level via Spring Boot auto-configuration.
- Use `Introspection.INTROSPECTION_DISABLED` in `GraphQLContext` when per-request or role-based policies are needed.
- Never combine global disable with a requirement for some roles to re-enable it; the global flag cannot be overridden by request context.
- Obtain roles from authenticated Spring Security; never trust a client-declared header or GraphQL variable.
- Keep `__typename` working for clients and normalized caches.
- Disable GraphiQL and the schema printer separately if not needed in production.
- Check HTTP, WebSocket, and other transports if they serve the same GraphQL schema.
- Never treat disabling introspection as authorization; protect resolvers and data independently.
- Never put secrets or internal implementation details in schema descriptions.
- Test `__schema`, `__type`, `__typename`, business fields, and secondary endpoints.
- Re-verify the policy whenever changing Spring Boot or GraphQL Java versions.

## 13. Practice exercise

Build an introspection policy for a library API:

1. Declare `Query.bookById` and type `Book` in SDL.
2. Send `__schema` and `__type` queries to observe the metadata returned when introspection is enabled.
3. Configure `spring.graphql.schema.introspection.enabled=false`.
4. Resend the two queries above and confirm GraphQL returns errors.
5. Send a query with `__typename` and confirm the field still works.
6. Disable GraphiQL and the schema printer in the production profile.
7. Write a `WebGraphQlInterceptor` allowing only authority `ROLE_SCHEMA_READER` to run introspection.
8. Test requests with the role, without the role, and anonymous.
9. Verify normal queries still require dedicated authorization in resolvers.
10. Try creating a custom `GraphQlSource` and verify whether the introspection property takes effect in the actual configuration.
11. Write smoke tests for `/graphiql` and `/graphql/schema`.
12. Explain why hiding the schema cannot replace authorization or rate limiting.

After this exercise, you should know how to choose between a global policy and a per-request policy, understand the role of `__typename`, and prove the policy with real queries rather than merely reading configuration files.

## 14. References

- [Spring Boot — Spring for GraphQL: Schema Introspection, GraphiQL and Schema Printer](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [GraphQL Java — Introspection API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/introspection/Introspection.html)
- [GraphQL Java — NoIntrospectionGraphqlFieldVisibility](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/schema/visibility/NoIntrospectionGraphqlFieldVisibility.html)
- [Spring for GraphQL — Server Transports and WebGraphQlInterceptor](https://docs.spring.io/spring-graphql/reference/transports.html)
- [OWASP GraphQL Cheat Sheet — Introspection and GraphiQL](https://cheatsheetseries.owasp.org/cheatsheets/GraphQL_Cheat_Sheet.html)

`Introspection`, field visibility APIs, and auto-configuration may vary across GraphQL Java and Spring Boot versions. In particular, `NoIntrospectionGraphqlFieldVisibility` was deprecated in GraphQL Java 22; prefer the `Introspection` API and check the Javadoc for the exact version managed by Spring Boot.
