# Hiding Sensitive Metadata in GraphQL

GraphQL has an **introspection** mechanism that allows clients to query the server about the published schema: its types, fields, arguments, directives, and descriptions. This mechanism is very useful for IDEs, API documentation, and client code generation. However, if a schema contains internal field names, descriptions of private workflows, or operations-only metadata, introspection can expose that information.

Hiding sensitive metadata needs to be addressed at two layers. First, design the schema and descriptions so they do not contain secrets or internal information that should not be publicized. Next, choose an introspection policy suited to the environment and audience. Disabling introspection only reduces schema discoverability; it does not replace authentication and authorization for data.

## What Can Introspection Reveal?

GraphQL provides meta-fields for schema discovery. Two common fields are:

- `__schema`: returns an overview of the schema, including the query root, mutation root, subscription root, types, and published directives.
- `__type(name: "...")`: inspects details of a single type by name, including fields, arguments, data types, enum values, and descriptions if present.

Example querying types and fields:

```graphql
query InspectSchema {
  __schema {
    queryType {
      name
    }
    types {
      name
      description
      fields {
        name
        description
      }
    }
  }
}
```

Clients can also inspect a single type:

```graphql
query InspectAccount {
  __type(name: "Account") {
    name
    description
    fields {
      name
      description
      args {
        name
        description
      }
    }
  }
}
```

Introspection does not return runtime data for users or database contents. It describes the API contract published by the server. Still, the schema structure can reveal information useful to someone mapping the attack surface, such as:

- Type and field names related to administration, billing, moderation, or internal operations.
- Arguments revealing how data is filtered, business states, or query parameters.
- Enum values exposing internal system states.
- Descriptions explaining workflows, integrated system names, error codes, or operational limits.
- Directives and deprecation reasons revealing API lifecycle metadata.
- URLs in directives such as `@specifiedBy` that may point to external docs or resources.

Introspection does not create an authorization vulnerability by itself. Risk arises when metadata exposes more than necessary or when the server relies on users not knowing field names to protect data.

## Descriptions in SDL Are Metadata Too

GraphQL SDL supports descriptions using multi-line strings placed before a type, field, argument, or enum value. These descriptions can be retrieved via introspection:

```graphql
"""Account information displayed to the user."""
type Account {
  id: ID!
  displayName: String!

  """Internal note from the operations team."""
  internalReviewNote: String
}
```

Descriptions are part of the schema and can be exposed to clients. Therefore, do not put the following in descriptions:

- Credentials, tokens, API keys, passwords, or connection strings.
- Hostnames, internal addresses, table names, or infrastructure details that should not be public.
- Exploit instructions, testing notes, or internal incident-response procedures.
- Personal data, customer data, or confidential organizational content.

Comments starting with `#` in SDL files do not become schema descriptions the way `"""..."""` description strings do. However, comments still reside in source code and can be exposed via repositories, artifacts, or build systems; do not use comments to store secrets.

## Do Directives Hide Fields from Introspection?

No. Directives describe metadata or control part of GraphQL behavior according to their defined locations and rules. Common directives serve different purposes:

| Directive | Effect | Automatically Hides Field from Schema? |
| --- | --- | --- |
| `@skip(if: ...)` | Skips a field during a single execution if the condition is true. | No. |
| `@include(if: ...)` | Includes a field during a single execution if the condition is true. | No. |
| `@deprecated(reason: ...)` | Marks a field or enum value as deprecated and can provide a reason. | No. The deprecation reason can be read by introspection. |
| `@specifiedBy(url: ...)` | Provides a URL describing a custom scalar's convention. | No. The URL can be exposed. |
| Custom directive | Attaches custom metadata or conventions to the schema. | No, unless the application implements a separate visibility mechanism. |

For example, `@skip` only controls a specific response:

```graphql
query AccountView($showEmail: Boolean!) {
  account(id: "acc-100") {
    id
    displayName
    email @include(if: $showEmail)
  }
}
```

The `email` field still exists in the schema and still appears when introspection lists the fields of `Account`. The directive only decides whether to resolve the field in that specific operation.

`@deprecated` is not a security tool either:

```graphql
type Account {
  id: ID!
  legacyCode: String @deprecated(reason: "Use accountReference instead")
  accountReference: String!
}
```

Clients can view `legacyCode` and the deprecation reason via introspection. Write concise reasons with sufficient migration guidance for clients and no internal notes.

## Custom Directives Marking Sensitive Data

An application can define a custom directive to label sensitive fields:

```graphql
directive @sensitive on FIELD_DEFINITION

type Account {
  id: ID!
  displayName: String!
  internalReviewNote: String @sensitive
}
```

The `@sensitive` directive in this example is only schema-declared metadata. GraphQL Java does not automatically know that a field with this directive must be hidden, require admin permissions, or be excluded from introspection. To enforce a rule, the application must implement handling for the directive, such as inspecting metadata during schema construction or checking permissions in the resolver.

The directive definition along with its metadata such as name, arguments, and permitted locations can be read via introspection. Standard GraphQL introspection does not provide a general way to list every location where a custom directive was applied. Even so, marking a field as sensitive does not make the field name disappear from the schema.

For data read permissions, a field resolver can check permissions before returning a value:

```java
@SchemaMapping(typeName = "Account", field = "internalReviewNote")
public String internalReviewNote(Account account) {
    authorizationService.checkCanReadInternalNote(account.getId());
    return accountService.getInternalReviewNote(account.getId());
}
```

This example protects the field value based on the current user. The name `internalReviewNote` can still be seen in the schema if introspection is enabled; callers can also attempt to query the field if they know its name, so the resolver must reject them if they lack permission.

## Introspection Policies by Environment

Introspection is very helpful during development:

- GraphiQL or IDEs can load the schema to suggest fields and arguments.
- Client generators can produce type-safe code from the schema.
- Integration teams can read documentation and inspect API changes.
- Contract tests can verify the published schema.

In production, organizations must decide whether the schema is public to all clients or restricted to internal tools and users. No single choice fits every API. A public API may intentionally publish its schema; an internal business API may restrict introspection based on operational policy.

A reference policy matrix:

| Environment | Suggested Policy |
| --- | --- |
| Local development | Enable introspection to support IDEs and experimentation. |
| CI and test | Enable for schema validation, client generation, and contract verification. |
| Staging | Enable with controls or require authentication for integration teams to test. |
| Production public API | Decide according to the published contract; keep secrets out of the schema. |
| Production private API | Can restrict or disable introspection based on security and operational requirements. |

What matters is keeping the policy consistent across instances and environments. If internal tools need introspection, you can provide schema docs exported during the CI pipeline or a dedicated endpoint/schema for the development team.

## Restricting Introspection in GraphQL Java

GraphQL Java provides `GraphqlFieldVisibility` to control which fields are visible in the schema. A built-in option is `NoIntrospectionGraphqlFieldVisibility`, which removes introspection fields such as `__schema` and `__type` from schema querying.

Example at the GraphQL Java layer when building the schema:

```java
import graphql.schema.GraphQLSchema;
import graphql.schema.visibility.NoIntrospectionGraphqlFieldVisibility;

GraphQLSchema restrictedSchema = GraphQLSchema.newSchema(existingSchema)
        .fieldVisibility(new NoIntrospectionGraphqlFieldVisibility())
        .build();
```

This snippet illustrates GraphQL Java's mechanism: the schema is built with field visibility that disallows introspection access. When integrating into Spring for GraphQL, apply this visibility when constructing `GraphQlSource`/`GraphQLSchema`, using the APIs of the GraphQL Java and Spring for GraphQL versions your project runs. An auto-configured `GraphQlSource` from Spring Boot must also be customized properly at the schema-building stage; adding a controller or directive to SDL does not disable introspection.

Do not copy a configuration from another version without verifying your actual dependencies. Schema-building APIs and how Spring Boot lets you customize `GraphQlSource` can vary across versions. After configuring, test `__schema` and `__type` directly against the running endpoint to confirm the policy is enforced.

### `__typename` Still Has Its Own Purpose

`__typename` is a meta-field that returns the concrete object type name of the current value. It is commonly used with interfaces, unions, and client caches. `NoIntrospectionGraphqlFieldVisibility` is intended to block schema discovery via `__schema` and `__type`; do not confuse that goal with removing `__typename` from every response.

For example, clients may still need:

```graphql
query Search {
  search(term: "spring") {
    __typename
    ... on Book {
      title
    }
    ... on Article {
      title
    }
  }
}
```

## Schema Visibility Does Not Replace Authorization

There are three distinct goals to separate:

1. **Hiding metadata:** restricting callers from discovering types, fields, arguments, and descriptions.
2. **Hiding fields in the schema:** creating a schema view that does not expose certain fields or types to a group of clients.
3. **Protecting data:** authenticating callers and deciding whether they have permission to read or mutate a value.

Field visibility can prevent a field from appearing in a schema view and from being queried through that schema. However, that is API surface control. Every sensitive field still needs authorization in its resolver or service, because visibility configuration can change, another endpoint might serve the full schema, or a client might call another internal API.

In particular, disabling introspection does not make business fields disappear. If `internalReviewNote` still exists in the running schema, a client that knows the field name can still send an operation directly. The server must enforce access permissions at execution time.

### Do Not Assume Schema Visibility Changes Per User Automatically

`GraphqlFieldVisibility` is a schema/runtime configuration. Do not assume that merely checking roles inside a resolver causes introspection to hide fields per user. If a system genuinely needs different schema views for different client groups, design separate schemas or `GraphQlSource` instances for each audience, and control endpoints and caches according to that policy.

Creating separate schemas per user can increase complexity, memory usage, and startup cost. It is usually easier to operate a public schema and an internal schema with separate endpoints, authentication, and documentation. Whether using one schema or multiple, data access permissions must still be checked on the server.

## Other Channels That Can Leak Metadata

Disabling introspection does not guarantee all API information stays private. Metadata can appear in:

- Error messages that suggest valid field names or reveal type names.
- API documentation, SDL schemas, generated files, source maps, or frontend JavaScript bundles.
- Request/response logs, monitoring dashboards, or tracing systems.
- Repositories, build artifacts, container images, or distributed packages.
- Internal endpoints exposed externally due to reverse proxy or network misconfiguration.

Therefore, control error messages, documentation access, logs, and how schemas are distributed. Errors returned to clients should be helpful enough to handle the request without exposing stack traces, infrastructure layout, or unnecessary internal details.

## Testing Introspection Policies and Field Protection

When implementing introspection restrictions or field protection, verify these cases:

- `__schema` requests are rejected or inaccessible in environments with introspection disabled.
- `__type(name: ...)` requests are restricted accordingly.
- Valid business queries continue working.
- `__typename` still works if clients need it for interfaces/unions.
- Unauthorized users cannot read sensitive fields even if they know the exact field name.
- Authorized users receive only data within their scope.
- Descriptions, deprecation reasons, and directive metadata contain no secrets.
- GraphiQL, code generation, and integration tools are re-verified if they depend on introspection.
- All production instances apply the same configuration and internal endpoints are not exposed externally.

An example test with `GraphQlTester` for a protected field can verify an error or null value according to the chosen contract:

```java
@Test
void unauthorizedUserCannotReadInternalNote() {
    graphQlTester.document("""
        query {
          account(id: "acc-100") {
            internalReviewNote
          }
        }
        """)
        .execute()
        .errors()
        .verify();
}
```

This test assumes the application's policy returns an execution error when permissions are insufficient. If the API contract chooses to return `null` or conceal resource existence, test that exact behavior and check `errors` accordingly. What matters is that sensitive data never appears in the response.

## Common Pitfalls

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| Added `@sensitive` but introspection still shows the field | Custom directive only attaches metadata and does not alter visibility automatically. | Configure field visibility or a separate schema view; still check permissions in the resolver. |
| Used `@skip` yet the field still appears in the schema | `@skip` only affects a single operation. | Use introspection/schema visibility policies if the goal is restricting schema discovery. |
| Disabled `__schema` yet clients still query known field names | The field still exists in the running schema. | Add authorization in the resolver/service or omit the field from the appropriate schema view. |
| Tooling cannot load the schema in production | Introspection has been restricted. | Provide a controlled schema artifact or an internal endpoint requiring authentication. |
| Descriptions leak internal information | Operational notes were placed into SDL descriptions. | Review and write descriptions tailored for API consumers. |
| One instance still allows introspection | Inconsistent environment config or a custom `GraphQlSource` missed the policy. | Test all instances and verify the actual schema at startup. |

## Key Takeaways

Introspection allows clients to explore a schema through `__schema` and `__type`. Metadata can include type/field names, arguments, descriptions, enum values, and directives. Never put secrets or internal notes inside SDL descriptions, deprecation reasons, or directive metadata.

Directives such as `@skip`, `@include`, `@deprecated`, and custom directives do not automatically hide fields from the schema. GraphQL Java provides `GraphqlFieldVisibility` and `NoIntrospectionGraphqlFieldVisibility` to restrict introspection; in Spring for GraphQL, apply the policy during `GraphQlSource`/schema construction according to your running version.

Finally, hiding metadata only reduces API discoverability. It does not replace authorization. Every field containing sensitive data must verify permissions on the server, even when introspection is disabled.
