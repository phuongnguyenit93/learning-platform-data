# Deprecated Field

## 1. What Is a Deprecated Field?

A GraphQL schema is a contract between the server and clients. Once an API is used by many applications, renaming or deleting a field can break running queries from older clients. In practice, servers usually need a transition period to introduce the new field, guide clients through migration, and confirm the old field is no longer in use before removing it.

GraphQL provides the standard `@deprecated` directive to mark a field or enum value as no longer recommended. This metadata informs schema readers, IDEs, and developers which API parts are being replaced, while also displaying warnings and migration reasons.

For example, suppose an API previously exposed a `name` field and wants to transition to `displayName`:

```graphql
type User {
    id: ID!
    name: String! @deprecated(reason: "Use displayName instead.")
    displayName: String!
}
```

In this example, `name` still exists in the schema and older clients can still query it. The directive simply marks the field as outdated and provides guidance to move to `displayName`. The server decides when to remove the field in a future schema change.

## 2. `@deprecated` Syntax in SDL

`@deprecated` is a directive predefined by GraphQL. There is no need to declare this directive in the schema yourself. You can place it after a field's return type:

```graphql
type Product {
    id: ID!
    oldPrice: Float @deprecated(reason: "Use price instead.")
    price: Float!
}
```

`reason` is a `String` argument. If `reason` is omitted, the default value according to the specification is `No longer supported`:

```graphql
type Product {
    oldPrice: Float @deprecated
    price: Float!
}
```

In real-world projects, you should provide a clear reason and point out the replacement field. The default reason indicates that the field is no longer supported, but does not help clients figure out how to update their queries.

### Marking a Field on the Root Query

The directive can be applied to fields on root types such as `Query` or `Mutation`:

```graphql
type Query {
    user(id: ID!): User

    userByUsername(username: String!): User
        @deprecated(reason: "Use user(id:) instead.")
}
```

Clients should migrate from `userByUsername` to `user` and pass the appropriate identifier. During the transition period, both fields can coexist so older client versions continue working.

### Marking an Enum Value

`@deprecated` can also mark an enum value:

```graphql
enum OrderStatus {
    PENDING
    PAID
    FULFILLED
    SHIPPED @deprecated(reason: "Use FULFILLED instead.")
}
```

Clients should stop sending or relying on `SHIPPED` once a replacement value exists. The server needs to maintain compatible handling during the migration period, especially if the enum value appears in stored data or is sent by multiple clients.

## 3. `@deprecated` Neither Deletes the Field Nor Blocks Queries

This is a critical point when designing an API lifecycle:

- A field marked deprecated remains part of the schema.
- Clients can still send queries using that field.
- GraphQL still validates and executes the field's resolver normally.
- Deprecation metadata helps tools and humans identify fields that should be replaced.
- The field only disappears when the server actually removes its definition from the schema.

For example, both of the following queries remain valid when the schema has `name` and `displayName`:

```graphql
query OldClient($id: ID!) {
    user(id: $id) {
        name
    }
}

query NewClient($id: ID!) {
    user(id: $id) {
        displayName
    }
}
```

After removing `name` from the schema, `OldClient`'s query will be rejected by validation because the field no longer exists. Therefore, marking a field deprecated is preparation for changing the contract, not an automatic mechanism for migrating clients to the new field.

`@deprecated` is also not a security mechanism. Do not use this directive to hide data, revoke permissions, or prevent users from querying a field. If you need to deny access, design server-side authorization and evolve the API through an appropriate process.

## 4. Reading Deprecation Information via Introspection

GraphQL introspection allows clients or tools to query the schema for types, fields, arguments, and directives. For fields, introspection provides two properties:

- `isDeprecated`: indicates whether the field is marked deprecated.
- `deprecationReason`: the reason declared in the directive, or the default value if no reason was passed.

By default, the introspection `fields` field omits deprecated fields. You must pass `includeDeprecated: true` to retrieve older fields as well:

```graphql
query UserFields {
    __type(name: "User") {
        name
        fields(includeDeprecated: true) {
            name
            isDeprecated
            deprecationReason
        }
    }
}
```

Illustrative response:

```json
{
  "data": {
    "__type": {
      "name": "User",
      "fields": [
        {
          "name": "id",
          "isDeprecated": false,
          "deprecationReason": null
        },
        {
          "name": "name",
          "isDeprecated": true,
          "deprecationReason": "Use displayName instead."
        },
        {
          "name": "displayName",
          "isDeprecated": false,
          "deprecationReason": null
        }
      ]
    }
  }
}
```

`__type(name: "User")` requests information about the `User` type. `includeDeprecated: true` ensures older fields still appear in the list so tools can read the metadata and emit warnings.

### Enum Value Introspection

For enums, use `enumValues(includeDeprecated: true)`:

```graphql
query OrderStatusValues {
    __type(name: "OrderStatus") {
        name
        enumValues(includeDeprecated: true) {
            name
            isDeprecated
            deprecationReason
        }
    }
}
```

Documentation generators or schema inspection tools can use this result to list enum values that need migration. Without enabling `includeDeprecated`, deprecated values may not appear in the list.

## 5. Writing Useful Deprecation Reasons

The deprecation reason is guidance for API consumers. A good reason should be concise, specific, and actionable.

Good example:

```graphql
type User {
    fullName: String
        @deprecated(reason: "Use displayName; it preserves the formatted name shown to users.")
    displayName: String!
}
```

The reason specifies the new field to use and explains the key difference. Things to consider including in the reason:

- The replacement field or enum value name.
- How to convert arguments if the new field has a different signature.
- Differences in data semantics or return format.
- A link to migration documentation if the organization maintains stable public docs.
- A sunset date if there is an official schedule and you can honor the commitment.

Avoid vague reasons like `Old field`, `Deprecated`, or `Do not use`. These phrases do not help consumers understand how to update their queries.

## 6. Maintaining Resolvers in Spring for GraphQL

In Spring for GraphQL, schema-first SDL is typically placed in `src/main/resources/graphql/`. The `@deprecated` directive is declared directly in the schema:

```graphql
type User {
    id: ID!
    name: String! @deprecated(reason: "Use displayName instead.")
    displayName: String!
}

type Query {
    user(id: ID!): User
}
```

During the transition period, resolvers for the old and new fields can share the same data source or business rule:

```java
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class UserController {

    @SchemaMapping(typeName = "User", field = "name")
    public String legacyName(User user) {
        return user.displayName();
    }

    @SchemaMapping(typeName = "User", field = "displayName")
    public String displayName(User user) {
        return user.displayName();
    }
}
```

This example assumes `User` is a Java record with a `displayName()` method. Both GraphQL fields return the same business value, while the schema metadata indicates that `name` is the legacy field.

`@SchemaMapping` maps a Java method to a field in the schema. The `@deprecated` directive belongs to the SDL contract and is exposed by GraphQL Java via introspection. Do not assume that merely adding the Java `@Deprecated` annotation to a method automatically updates deprecation metadata in the schema; declare the directive explicitly in SDL.

### Do Not Remove the Resolver Immediately When Marking Deprecated

If you delete the resolver or stop supplying data while the field still exists, older clients may receive execution errors even though their queries remain valid against the schema. During the transition period, keep compatible behavior for the old field, or ensure a default resolver can supply the right value.

Only after confirming that clients no longer depend on the field should the development team remove the SDL definition and obsolete logic.

## 7. Safe Workflow for Replacing a Field

Suppose the API currently has `user.fullName` and wants to replace it with `user.displayName`. You can roll this out in steps:

1. **Design the new field:** define its type, nullability, semantics, and how the resolver supplies data.
2. **Add the new field:** add `displayName` to the SDL and implement its resolver.
3. **Mark the old field:** add `@deprecated(reason: "Use displayName instead.")` to `fullName`.
4. **Update documentation and clients:** instruct development teams to migrate queries, fragments, generated types, and response handling code to the new field.
5. **Track usage:** collect appropriate operation or field usage data to identify which clients still use the old field.
6. **Announce the deadline:** if there is a removal schedule, publish the date clearly and coordinate with client-owning teams.
7. **Confirm zero remaining dependencies:** check traffic, persisted operations, app versions, and known integrations.
8. **Remove the old field:** remove the SDL definition and resolver in a controlled change; verify schema diff and remaining active clients.

Not every project requires a long period for every step. The transition window depends on the number of clients, ability to update synchronously, and how critical the field is.

## 8. Tracking Usage of Deprecated Fields

Introspection tells you which fields are marked deprecated, but not which clients are actually calling them. To decide when to remove a field, the server needs usage data from live traffic.

Data sources you can use:

- Logs or metrics grouped by operation name and executed fields.
- GraphQL instrumentation or observability to record resolver/field usage.
- A persisted query registry if the system manages registered operations.
- App version or client identity metadata if requests provide it and policies allow.
- Inspecting queries in the source code of organization-managed clients.

Collect enough data to identify dependencies without logging sensitive variables or unnecessary full payloads. A field absent from traffic for a few days is not necessarily safe to remove if there are clients running on long cycles, older mobile apps, or infrequently invoked integrations.

If there are multiple independent clients, agree on how usage is measured and a zero-request threshold before planning removal. For persisted queries, also inspect operations that are registered even if rarely executed.

## 9. Deprecation and Schema Compatibility

Marking a field deprecated is usually a backwards-compatible change because the field still exists and older clients can still query it. Removing a field is a breaking change for operations that reference that field.

| Change | Typical Impact |
| --- | --- |
| Adding a new field | Compatible with existing clients |
| Adding `@deprecated` to an existing field | Preserves queryability; adds warning metadata |
| Changing the `@deprecated` reason | Changes guidance without altering data structure |
| Keeping the old field and adding a compatible resolver | Old and new clients can operate concurrently |
| Removing a field from the schema | Clients still querying that field fail validation |
| Removing an enum value still used by clients | Can render older operations or data invalid |

Before deleting, inspect the schema diff, run representative operation tests, and review persisted queries. For APIs used across multiple organizations, a formal versioning process or clearly published sunset schedule may be required.

## 10. Testing Deprecated Metadata

You can use GraphQlTester to verify that introspection returns the expected metadata:

```java
graphQlTester.document("""
    query UserFields {
        __type(name: "User") {
            fields(includeDeprecated: true) {
                name
                isDeprecated
                deprecationReason
            }
        }
    }
    """)
    .execute()
    .path("__type.fields")
    .entityList(UserFieldMetadata.class)
    .satisfies(fields -> {
        UserFieldMetadata legacy = fields.stream()
            .filter(field -> field.name().equals("name"))
            .findFirst()
            .orElseThrow();

        assertThat(legacy.isDeprecated()).isTrue();
        assertThat(legacy.deprecationReason())
            .isEqualTo("Use displayName instead.");
    });
```

The DTO used in the example can be declared as a Java record:

```java
public record UserFieldMetadata(
        String name,
        boolean isDeprecated,
        String deprecationReason) {
}
```

The snippet focuses on demonstrating how to read introspection; depending on the Spring GraphQL version and mapper configuration, you may need to adjust the DTO type or data extraction approach.

In addition to introspection, verify that the old field still executes during the transition period:

```graphql
query LegacyUser($id: ID!) {
    user(id: $id) {
        name
    }
}
```

And that the new field returns the correct data:

```graphql
query CurrentUser($id: ID!) {
    user(id: $id) {
        displayName
    }
}
```

When it is time to remove the old field, add tests confirming the schema no longer contains that field and that new operations remain valid. Do not inspect only the SDL file; test the runtime schema after Spring for GraphQL initializes it.

## 11. Common Pitfalls When Using `@deprecated`

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| Old field does not appear in introspection | Querying `fields` without `includeDeprecated: true` | Enable `includeDeprecated` when reading the full schema |
| Clients can still query the deprecated field | This is expected behavior; the directive does not block execution | Keep a compatible resolver until removal criteria are met |
| IDE does not show warnings | Tooling has not read metadata or schema cache is stale | Refresh schema and check the tool's deprecation support |
| Reason does not help clients migrate | Message is too generic or omits the replacement field | Write a reason with the replacement name and concrete guidance |
| Old field query validates but resolver errors | Logic or resolver was removed too early | Maintain the resolver until migration is complete |
| Removing field breaks old clients | Usage was not measured or persisted operations were not checked | Review traffic, schema diff, and clients before removal |
| Assuming Java `@Deprecated` automatically updates SDL | Java annotation and GraphQL directive are separate metadata | Declare `@deprecated` in the SDL schema |
| Using deprecation to protect data | The directive is only advisory metadata | Use server-side authorization and access control |

## 12. Checklist Before Removing a Deprecated Field

- [ ] Replacement field already exists with equivalent or clearly documented data semantics.
- [ ] Old field has `@deprecated` with a concrete reason.
- [ ] Old resolver continues working throughout the transition period.
- [ ] Migration documentation explains how to update queries and generated types.
- [ ] Introspection returns accurate `isDeprecated` and `deprecationReason`.
- [ ] Field usage has been tracked via traffic, instrumentation, or persisted operations.
- [ ] Low-frequency clients, older mobile apps, and periodic integrations have been accounted for.
- [ ] Removal schedule has been communicated to client-owning teams if needed.
- [ ] Schema diff and operation tests have been run prior to removal.
- [ ] SDL definition, resolver, and related logic are removed only after all dependencies are gone.

## Conclusion

The `@deprecated` directive lets you mark fields or enum values as no longer recommended and publish the replacement reason in the GraphQL schema. This metadata is read via introspection using `isDeprecated` and `deprecationReason`; when older fields are needed, the query must specify `includeDeprecated: true`.

In Spring for GraphQL, declare `@deprecated` directly in SDL and keep compatible resolvers during the transition period. Marking a field deprecated does not automatically block queries, delete the field, or replace authorization. Only remove the field after guiding clients through migration, measuring usage, checking dependent operations, and confirming the schema change is safe.
