# Introspection Queries in GraphQL

**Introspection** is the mechanism that allows clients or tools to query a GraphQL schema's metadata directly through the GraphQL API. Instead of manually reading SDL files, a client can ask the server which types, fields, arguments, return types, and directives are defined.

Introspection is especially useful for developer tools such as GraphQL IDEs, API documentation generators, code generators, and clients that need to inspect the API contract. In Spring for GraphQL, GraphQL Java provides introspection support; you can use `GraphQlTester` to verify schema metadata in tests.

## 1. How Does Introspection Work?

GraphQL defines several meta-fields and meta-types specifically for schema discovery. The most commonly used elements are:

| Element | Role |
|---|---|
| `__schema` | Queries the overall schema, including root types, type list, and defined directives. |
| `__type(name: String!)` | Queries metadata for a single type by name. |
| `__typename` | Returns the concrete object type name being resolved at runtime. |
| `__Type` | Introspection type describing a GraphQL type such as object, interface, union, scalar, or enum. |
| `__Field`, `__InputValue`, `__EnumValue`, `__Directive` | Describe fields, arguments/input fields, enum values, and directives. |

`__schema` and `__type` are meta-fields available on the query root. `__typename` can be selected on objects, interfaces, and unions to identify the concrete type. `__typename` often appears in business queries, whereas `__schema` and `__type` are mainly used to explore the schema contract.

## 2. Querying a Schema Overview with `__schema`

The following query retrieves the root type names, type list, and directives published by the schema:

```graphql
query SchemaOverview {
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
        types {
            kind
            name
            description
        }
        directives {
            name
            description
            locations
            args {
                name
                description
            }
        }
    }
}
```

Meaning of the fields:

- `queryType`: the object type acting as the entry point for query operations.
- `mutationType`: the root type for mutations; can be `null` if the schema does not declare a mutation root.
- `subscriptionType`: the root type for subscriptions; can be `null` if the schema does not support subscriptions.
- `types`: the list of types in the schema, including built-in GraphQL types and application-defined types.
- `directives`: the defined directives, along with their permitted locations and arguments.

Each item in `types` has `kind`, `name`, and `description`. `kind` indicates which category the type belongs to, such as `OBJECT`, `INTERFACE`, `UNION`, `SCALAR`, `ENUM`, or `INPUT_OBJECT`.

The `types` list can be quite long because it also includes built-in scalars and introspection types such as `String`, `Int`, `__Schema`, and `__Type`. When building documentation or code generators, clients usually filter out types prefixed with `__` or keep only application-scoped types.

## 3. Inspecting Details of a Type with `__type`

`__type(name: String!)` accepts a type name and returns metadata for that type. For example, to inspect the `Book` type:

```graphql
query InspectBook {
    __type(name: "Book") {
        kind
        name
        description
        fields {
            name
            description
            type {
                kind
                name
            }
        }
    }
}
```

If `Book` is an object type, `fields` lists the fields exposed by the object. Each field has a name, description, and return type. If the supplied name does not exist, `__type` returns `null`.

You can use a variable instead of a hardcoded type name:

```graphql
query InspectType($typeName: String!) {
    __type(name: $typeName) {
        name
        kind
        description
    }
}
```

Example variables:

```json
{
  "typeName": "Book"
}
```

### Inspecting Fields, Arguments, and Return Types

To generate more detailed documentation, you can also query arguments and default values:

```graphql
query InspectBookFields {
    __type(name: "Book") {
        name
        fields(includeDeprecated: true) {
            name
            description
            args {
                name
                description
                defaultValue
                type {
                    kind
                    name
                }
            }
            type {
                kind
                name
            }
            isDeprecated
            deprecationReason
        }
    }
}
```

`args` describes the arguments a field accepts. `defaultValue` is the GraphQL-syntax representation of the default value; it is returned as a string. `isDeprecated` and `deprecationReason` indicate whether the field is marked with `@deprecated`.

In the example above, `includeDeprecated: true` requests deprecated fields as well. If this parameter is omitted, deprecated fields may be hidden from the list depending on the introspection field's default.

## 4. Reading Different Type Categories

`__Type` provides introspection fields appropriate for each GraphQL type kind. Not every field has a value for every `kind`.

| `__Type` Field | Used For | Contents |
|---|---|---|
| `fields` | Object and interface | Fields provided by the type. |
| `interfaces` | Object and interface | Interfaces implemented or inherited by the type. |
| `possibleTypes` | Interface and union | Concrete object types that can appear at runtime. |
| `enumValues` | Enum | Declared enum values. |
| `inputFields` | Input object | Fields that can be sent in an input object. |
| `specifiedByURL` | Custom scalar | Specification URL of the scalar if declared with `@specifiedBy`. |

Example inspecting union members:

```graphql
query InspectSearchResult {
    __type(name: "SearchResult") {
        name
        kind
        possibleTypes {
            name
            kind
        }
    }
}
```

If `SearchResult` is a union of `Book` and `Author`, `possibleTypes` lists those two object types. This information is useful for code generators or clients that need to know which types inline fragments can target.

Example inspecting an enum:

```graphql
query InspectOrderStatus {
    __type(name: "OrderStatus") {
        kind
        enumValues(includeDeprecated: true) {
            name
            description
            isDeprecated
            deprecationReason
        }
    }
}
```

Example inspecting an input object:

```graphql
query InspectProductInput {
    __type(name: "ProductInput") {
        kind
        inputFields {
            name
            description
            defaultValue
            type {
                kind
                name
            }
        }
    }
}
```

On GraphQL versions that support the `includeDeprecated` argument on `inputFields`, you can pass `includeDeprecated: true` to also retrieve deprecated input fields. If the server uses an older version that does not support that argument, omit the parameter so the query remains compatible.

## 5. Understanding Types via `kind`, `name`, and `ofType`

When introspecting a field, `type.name` is sometimes `null`. This commonly happens when a field uses wrapper types such as Non-null (`!`) or List (`[]`). You need to traverse `ofType` to reach the inner type.

Important `kind` values:

- `SCALAR`: scalar types such as `String`, `Int`, `Float`, `Boolean`, `ID`, or custom scalars.
- `OBJECT`: object types such as `Book`.
- `INTERFACE`: interface types.
- `UNION`: union types.
- `ENUM`: enum types.
- `INPUT_OBJECT`: input object types.
- `LIST`: list wrapper.
- `NON_NULL`: non-null wrapper.

Example:

```graphql
type Query {
    book: Book!
    books: [Book!]!
}
```

For `book: Book!`, introspection returns a structure like:

```text
kind = NON_NULL
name = null
ofType:
  kind = OBJECT
  name = Book
```

For `books: [Book!]!`, the nested structure looks like:

```text
NON_NULL
  ofType: LIST
    ofType: NON_NULL
      ofType: OBJECT
        name: Book
```

Because `ofType` can be nested across multiple levels, introspection queries typically use a finite-depth fragment chain. GraphQL does not allow infinitely self-referencing fragments in a document; therefore, the client must include enough nesting levels for the schema it wants to inspect.

```graphql
query InspectBookType {
    __type(name: "Query") {
        fields {
            name
            type {
                ...TypeRef
            }
        }
    }
}

fragment TypeRef on __Type {
    kind
    name
    ofType {
        kind
        name
        ofType {
            kind
            name
            ofType {
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

A depth of four levels is an illustrative example, not a fixed GraphQL limit. If a schema has deeper wrapper types, extend the fragment accordingly. When writing general-purpose tooling, handle the case where a query did not fetch enough levels and do not mistake a wrapper's `name: null` for an invalid type.

## 6. Introspection and Directives

`__schema.directives` lets you inspect directives defined by the schema, including name, description, locations, and arguments:

```graphql
query InspectDirectives {
    __schema {
        directives {
            name
            description
            locations
            args {
                name
                description
                defaultValue
                type {
                    kind
                    name
                }
            }
        }
    }
}
```

The result can include built-in directives such as `include`, `skip`, `deprecated`, and `specifiedBy`, as well as the application's custom directives.

Distinguish between **directive definitions** and **applied directive locations**. Standard introspection allows discovering directive definitions, but not every GraphQL version exposes metadata about each place a directive was attached to a field or type in SDL. If you need to know exactly which fields have `@requiresRole` or `@sensitive`, inspect the SDL or use GraphQL Java's schema/AST APIs appropriate for your runtime version.

## 7. `__typename` in Business Queries

Unlike `__schema` and `__type`, `__typename` is commonly used directly inside business queries to determine an object's runtime type:

```graphql
query {
    search(keyword: "GraphQL") {
        __typename
        ... on Book {
            title
        }
        ... on Author {
            name
        }
    }
}
```

If an item is a `Book`, `__typename` returns `Book`; if it is an `Author`, it returns `Author`. The client can use this result to choose the right rendering logic.

`__typename` is also useful when working with interfaces, unions, and GraphQL client normalized caches. It does not replace a server-side `TypeResolver`: the server must still determine which GraphQL object type a Java object belongs to before returning results.

## 8. Using Introspection in Spring for GraphQL

Spring for GraphQL relies on GraphQL Java to build the schema and handle queries. When introspection is allowed in server configuration, clients can send `__schema` or `__type` queries to the GraphQL endpoint just like any other query.

You do not need to write a `@QueryMapping` for `__schema` or `__type`; they are GraphQL meta-fields. Your application's business resolvers are still registered normally.

You can verify the schema using `GraphQlTester` in tests:

```java
@GraphQlTest(BookController.class)
class SchemaIntrospectionTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @Test
    void exposesBookType() {
        graphQlTester.document("""
                query {
                    __type(name: "Book") {
                        name
                        kind
                        fields {
                            name
                        }
                    }
                }
                """)
            .execute()
            .path("__type.name").entity(String.class).isEqualTo("Book");
    }
}
```

This is an illustrative example; imports are omitted and the schema declaring `Book` must be loaded in the test context. `BookService` is mocked so the controller can be instantiated; depending on the Spring Boot version, the mock bean annotation may be `@MockitoBean` or `@MockBean`. You can expand assertions to verify required fields, return types, directives, or union members. This helps catch unexpected schema changes early during testing.

If introspection is disabled in application configuration, tests must either use a configuration that permits introspection or inspect the schema directly via an appropriate API. The exact toggle mechanism depends on the Spring Boot and GraphQL Java versions used by your project; do not copy a configuration property from another version without verifying your current dependencies.

## 9. Practical Uses of Introspection

Introspection is not only for GraphQL IDEs. Common applications include:

| Use Case | How It Works |
|---|---|
| API documentation generation | Reads types, fields, arguments, descriptions, and deprecation metadata to generate docs. |
| Code generation | Generates client data types, models, and operation helpers from the schema. |
| Compatibility checks | Compares schemas across releases to detect removed fields, type changes, or nullability changes. |
| Developer tooling | GraphQL IDEs use metadata to suggest fields, arguments, and provide autocomplete. |
| Contract testing | Verifies that the schema contains expected types, fields, union members, and directives. |
| Schema analysis | Enumerates objects, interfaces, unions, enums, and relationships between types. |

For example, a CI pipeline can query schema introspection from a test environment and compare it with the previous release's schema. If a `String` field changes to `String!`, that may be a contract change affecting clients because the server is making a stricter nullability guarantee.

## 10. Security and Limitations of Introspection

Introspection exposes the API structure: type names, fields, arguments, descriptions, directives, and type relationships. This is helpful for legitimate clients, but also lets outsiders understand the API surface if the endpoint is public.

Some systems restrict introspection in production or require appropriate access permissions. Keep in mind:

1. Disabling introspection does not replace authentication and authorization for business fields.
2. Do not rely on hiding the schema to protect data; resolvers and services must still enforce access control.
3. If introspection is enabled for internal tools, control who can access the endpoint and which environments allow it.
4. Review schema descriptions to avoid leaking internal information, system names, or sensitive implementation details in public metadata.
5. Some tools require introspection to operate; weigh the impact before disabling it completely in development or integration environments.

Large introspection queries can return substantial metadata and consume resources. Servers can apply query size, depth, complexity limits, or endpoint-specific policies. Design these limits alongside your overall GraphQL protection mechanisms.

## 11. Common Pitfalls

**Confusing `__typename` with `__type`.** `__typename` returns the name of the object type being resolved in a query; `__type(name:)` queries metadata for a type by name.

**Assuming `__schema.types` only contains application-created types.** The list also includes built-in scalars and introspection types. Filter by `kind` or name when generating documentation.

**Ignoring `ofType`.** If a field is `String!` or `[Book!]!`, the wrapper's `name` can be `null`. Traverse through `ofType` to determine the underlying type.

**Querying a type reference fragment that is too shallow.** Multi-level wrappers can be truncated if the fragment only reads one or two levels of `ofType`. Increase depth to fit your schema and handle insufficient depth gracefully.

**Assuming introspection always shows applied directives.** Standard introspection primarily exposes directive definitions. To know which directives are attached to a specific field, inspect SDL or the appropriate AST API.

**Using introspection as a security mechanism.** Hiding the schema does not stop clients from calling a field if they know its name and the endpoint permits it. Protect resolvers and data with real authorization.

**Not checking GraphQL versions.** Introspection arguments such as `includeDeprecated` on input fields can vary across versions. Ensure queries match the introspection schema the server actually provides.

## Conclusion

Introspection queries allow discovering a GraphQL schema via `__schema`, `__type`, and introspection types such as `__Type`, `__Field`, `__InputValue`, and `__Directive`. They power documentation generation, code generation, contract checking, and client API exploration. When using them with Spring for GraphQL, verify metadata with `GraphQlTester`, handle wrapper structures via `ofType`, check introspection availability in your deployment environment, and always enforce security in resolvers and services.
