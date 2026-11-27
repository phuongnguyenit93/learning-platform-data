# Schema Introspection in Production

GraphQL introspection is the mechanism that lets clients ask the server about the deployed schema itself: what types exist, which fields, which arguments, what return types, and which fields are deprecated. This mechanism is very useful for GraphiQL, IDEs, code generation, API documentation, and testing tools.

In production, introspection should be treated as an API metadata access capability. Enabling or disabling it should depend on the target consumers, how public the schema is, and operational requirements. With Spring for GraphQL, distinguish clearly between introspection queries, the GraphiQL UI, and the schema printer endpoint; these are related but independent features.

## 1. What Is Introspection?

GraphQL defines meta-fields so clients can explore the schema:

- `__schema`: queries overall schema information, including root operation types, the list of types, and directives.
- `__type(name: ...)`: queries details of a single type by name, such as fields, arguments, return types, and descriptions.
- `__typename`: retrieves the concrete object type name of a value returned at runtime.

Example querying the root query type name and some types in the schema:

```graphql
query InspectSchema {
    __schema {
        queryType {
            name
        }
        types {
            name
            kind
        }
    }
}
```

Querying details of the `Product` type:

```graphql
query InspectProduct {
    __type(name: "Product") {
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
                ofType {
                    kind
                    name
                }
            }
        }
    }
}
```

An introspection response reveals that `Product` is an object type, which fields it has, and what types those fields return. For wrappers such as List and Non-Null, type information may be nested inside `ofType`; introspection tools typically query recursively to reconstruct full types like `[Product!]!`.

`__typename` serves a different purpose: it indicates the concrete object type of a value in the response, commonly used with interfaces, unions, and inline fragments. In many applications, clients still need `__typename` even when full schema discovery is restricted.

## 2. How Does Introspection Help During Development?

GraphQL tools use introspection for many tasks:

- GraphiQL and IDEs display fields, arguments, data types, and descriptions as users write queries.
- Code generators create models, types, and client APIs from the schema.
- Documentation tools build references for each type, field, and directive.
- Testing tools or schema registries fetch schemas to compare changes.
- Integration tools can verify the server implements the contract clients expect.

For internal APIs, introspection can reduce the effort needed to keep documentation synchronized between server and client teams. However, tools should pull the schema in CI or from a trusted schema registry if they do not need access to production endpoints.

## 3. Risks of Leaving Introspection Publicly Open

Introspection itself does not return user business data. It returns API metadata. Even so, schema metadata can help outsiders understand the structure and locate targets to probe:

- Query and mutation names reveal the capabilities the API exposes.
- Fields and arguments can hint at business workflows, filters, or administrative features.
- Data types and nullability help predict how the server handles inputs and outputs.
- Descriptions, deprecation reasons, and directives can leak design information or implementation details if written too specifically.
- The type list can expose unreleased API parts or legacy features still present in the schema.

This information can aid reconnaissance and make endpoint probing easier. However, disabling introspection does not replace authentication, authorization, or input validation. If an administrative mutation can still be invoked without proper permissions, hiding the schema does not fix that vulnerability.

Therefore, evaluate introspection alongside other defense layers: authentication, field-level authorization, validation, query depth/complexity limits, rate limiting, and logging.

## 4. Distinguishing Introspection, GraphiQL, and Schema Printer

These three capabilities are often confused:

| Capability | Function | Effect When Disabled |
| --- | --- | --- |
| Introspection query | Allows `__schema` and `__type` queries to explore the schema | Tools cannot load the schema through the introspection endpoint. |
| GraphiQL | Web UI for writing and running GraphQL queries | Users no longer have the GraphiQL UI at the configured path. |
| Schema printer | Exports the schema as SDL via a dedicated endpoint when enabled | Clients cannot download SDL via the schema printer endpoint. |

Disabling GraphiQL does not automatically disable introspection. Conversely, disabling introspection does not necessarily remove the GraphiQL UI if it is still served; however, its documentation/schema explorer pane may fail to load the schema.

The schema printer is also a separate metadata-export channel. If enabled in production, protect it just like an API documentation endpoint, or disable it if there is no operational need.

## 5. Configuring UI and Schema Printer per Environment

Spring Boot provides properties to control GraphiQL and the schema printer. Configure them explicitly per profile to avoid accidentally enabling developer tools in production.

Example `application-dev.properties`:

```properties
spring.graphql.graphiql.enabled=true
spring.graphql.schema.printer.enabled=true
```

Example `application-prod.properties`:

```properties
spring.graphql.graphiql.enabled=false
spring.graphql.schema.printer.enabled=false
spring.graphql.schema.introspection.enabled=false
```

When running the production profile:

```bash
java -jar app.jar --spring.profiles.active=prod
```

`spring.graphql.schema.introspection.enabled=false` disables introspection in Spring Boot's auto-configuration. By default introspection is enabled because tools like GraphiQL require it. The other two properties control GraphiQL and the schema printer independently.

Do not rely solely on profiles to protect endpoints if a profile can be unintentionally overridden. Verify the final configuration in the deployment environment, check environment variables and command-line flags, and include support-endpoint status checks in deployment verification.

## 6. Disabling Introspection in Spring Boot

For applications using default GraphQL auto-configuration, the official property to disable introspection is:

```properties
spring.graphql.schema.introspection.enabled=false
```

When this property is applied, introspection queries such as `__schema` and `__type` are no longer available. Place the property in your production profile or corresponding deployment configuration. Do not just disable GraphiQL and assume the schema is hidden; configure introspection separately.

If the application declares its own `GraphQlSource` bean, the default `GraphQlSource` auto-configuration may no longer apply. In that case, check how your Spring Boot version applies the introspection property to custom sources and apply equivalent configuration on the actual GraphQL runtime if needed. Do not create a separate GraphQL instance that the HTTP handler does not use.

After configuring, always verify with requests against the real endpoint. Send both a `__schema` query and a `__type` query; verify that schema metadata cannot be retrieved under the production profile. Behavior may differ if a custom bean replaces auto-configuration.

Restricting introspection does not mean removing `__typename`. `__typename` is a meta-field used to determine runtime object types and is often still required by clients handling interfaces/unions, caching, and fragments.

## 7. Introspection Policies by Environment and Audience

No single policy fits every system. Consider these options:

| System Type | Suggested Policy |
| --- | --- |
| Local development | Enable introspection and GraphiQL for rapid schema exploration. |
| CI/test | Allow introspection in isolated environments for contract testing and generating client artifacts. |
| Internal staging | Open only to authorized users or internal networks; optionally enable schema explorer tools as needed. |
| Public production API | Weigh benefits for the developer ecosystem; if unnecessary, restrict introspection by endpoint or appropriate user group. |
| Private production API | Prefer requiring authentication and restricting schema metadata access by role. |

Some organizations keep introspection enabled on public APIs because documentation and code generation are part of the developer experience. In that case, review the schema so descriptions contain no secrets, internal details, or information that should not be public. Sensitive operations and fields must still be protected independently.

For private APIs, you might allow introspection only from service accounts or administrative networks. Enforce this policy at a request/runtime layer that can authenticate the principal, not merely by inspecting client-supplied operation names. If filtering operations via AST, account for fragments, aliases, and multiple operations in the same document; naive string matching is easy to bypass or prone to false positives.

## 8. Defense in Depth for the Schema

Introspection is only one part of the API surface. A production configuration should combine multiple safeguards:

1. **Authentication:** identify the caller using an appropriate mechanism such as sessions, OAuth2/JWT, or an API gateway.
2. **Authorization:** check permissions at the operation, field, or service/domain layer; never rely on clients not knowing a field name.
3. **Input validation:** validate values, size limits, numeric ranges, formats, and cross-field relationships.
4. **Query depth and complexity:** limit deeply nested queries or requests asking for excessive data in one call.
5. **Rate limiting:** limit request frequency per user, token, or client.
6. **Timeouts and resource limits:** prevent long-running queries from exhausting workers, database connections, or memory.
7. **Logging and monitoring:** log errors, anomalous queries, and endpoint usage without logging sensitive data.
8. **Schema governance:** review schema changes, deprecations, and descriptions prior to release.

In Spring Security, securing the GraphQL HTTP path is a necessary layer, but field-level authorization must still be enforced when fields within the same operation have different requirements. A single request can contain many fields, so checking access to `/graphql` alone is insufficient.

## 9. Managing Schemas Without Relying on Production Introspection

If your goal is generating documentation, generating clients, or checking schema compatibility, you do not have to query production every time. A CI/CD pipeline can:

- Pull SDL from source control or artifacts built alongside the application version.
- Run schema syntax and validation checks in CI.
- Compare the new schema against the released version to detect breaking changes.
- Generate client models and documentation from reviewed SDL.
- Store schema artifacts tagged with version, commit, or build identifiers.
- Verify the running schema in staging before promoting to production.

This gives client schemas and deployed schemas a clear source of truth while reducing the need to grant broad introspection access in production. If runtime schema verification is still needed, use a service account with restricted permissions and a controlled pipeline check step.

## 10. Testing Introspection Policies

Do not rely on inspecting properties files alone. Send actual requests to the GraphQL endpoint to verify final behavior.

Example query to test introspection:

```graphql
query IntrospectionCheck {
    __schema {
        queryType {
            name
        }
    }
}
```

In an environment that permits introspection, the response should contain `data.__schema.queryType.name`. In an environment where introspection is disabled, the request must be rejected according to policy and the response should include an appropriate error. Also test `__type(name: "Product")` to ensure both introspection entry points are handled.

Example test using `GraphQlTester`:

```java
@Test
void introspectionIsRejectedWhenProductionPolicyDisablesIt() {
    graphQlTester.document("""
            query {
                __schema {
                    queryType { name }
                }
            }
            """)
        .execute()
        .errors()
        .satisfy(errors -> assertThat(errors).isNotEmpty());
}
```

This test assumes `graphQlTester` is configured with the production policy. Error names and details may vary by GraphQL Java version; assert on behavior and error classification rather than depending on the exact full message. If your policy allows an admin group to introspect, test both authorized and unauthorized users.

In addition to introspection, verify separately:

- GraphiQL is not served in production if disabled.
- The schema printer endpoint is not served if disabled.
- `__typename` queries still work on objects/interfaces/unions if clients require them.
- Sensitive fields remain blocked for unauthorized users, even if they know the field names.
- Deep queries, large queries, and repeated requests are bounded by operational limits.

## 11. Pre-Production Checklist for GraphQL

1. Identify who needs to read schema metadata and why introspection is needed.
2. Decide whether introspection is public, role-restricted, or disabled at runtime.
3. Configure GraphiQL and the schema printer separately per profile; do not confuse them with introspection.
4. If disabling introspection, verify the property or custom configuration applies to the exact GraphQL runtime used by Spring's `GraphQlSource`.
5. Retain `__typename` if clients rely on runtime type information.
6. Protect operations and fields with independent authentication/authorization.
7. Enable validation, query depth/complexity limits, rate limiting, and appropriate timeouts.
8. Manage SDL in source control/CI or a schema registry so production introspection does not need to be opened to every tool.
9. Write integration tests for `__schema`, `__type`, `__typename`, GraphiQL, and the schema printer.
10. Verify effective configuration after deployment, including profiles, environment variables, and command-line overrides.

Schema introspection is a powerful tool for discovering and integrating GraphQL APIs. In production, deciding whether to enable or restrict it should be based on client needs and schema visibility. Whichever policy you choose, true security still comes from authentication, authorization, resource limits, and consistent schema governance.

Reference: [Spring Boot - Spring for GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html).
