# Non-null types in GraphQL SDL

In GraphQL, a field can return a value or `null`. By default, types in a schema allow `null`. When you want to guarantee a field always produces a value, append `!` to the type to create a **Non-null type**.

For example, `String` allows a result to be a string or `null`, whereas `String!` requires the result to be a string. This rule is part of the GraphQL contract between server and client. In Spring for GraphQL, the contract is declared in SDL, and Java resolvers must return data conforming to that contract.

## 1. Nullable types and Non-null types

By default, GraphQL types are nullable:

```graphql
type Product {
    name: String
    description: String
}
```

In this example, both `name` and `description` can return `null`. A valid response might be:

```json
{
  "data": {
    "product": {
      "name": "Keyboard",
      "description": null
    }
  }
}
```

Add `!` after a type to declare that the value cannot be `null`:

```graphql
type Product {
    id: ID!
    name: String!
    description: String
}
```

`id` and `name` must have values when GraphQL finishes resolving those fields. `description` can still be `null`. If the server returns `null` for `id` or `name`, GraphQL creates an execution error and applies the null propagation rules described later.

The `!` modifier does not mean a string must be non-empty. `String!` still accepts `""`; it only forbids `null`. If business logic requires a non-blank string, length bounds, or a specific format, the application must enforce those via validation or business logic.

## 2. Non-null with Lists

GraphQL allows combining `!` with list types. You must distinguish the nullability of the list itself from the nullability of each element inside the list.

| Syntax | Can list be `null`? | Can elements be `null`? |
|---|---|---|
| `[String]` | Yes | Yes |
| `[String]!` | No | Yes |
| `[String!]` | Yes | No |
| `[String!]!` | No | No |

Example declarations:

```graphql
type Product {
    tags: [String!]!
    aliases: [String]
    relatedIds: [ID!]
}
```

- `tags: [String!]!`: the list must always exist and every element must be a non-`null` string.
- `aliases: [String]`: the list may be `null`; if the list exists, an element may also be `null`.
- `relatedIds: [ID!]`: the list may be `null`, but if a list is present, every ID must be non-`null`.

With `tags: [String!]!`, both of the following responses are valid:

```json
{ "tags": ["mechanical", "wireless"] }
```

```json
{ "tags": [] }
```

An empty list is not `null`, so it remains valid. Non-null does not impose a requirement that the list have at least one element. If business rules require at least one element, validate that condition separately.

## 3. Null propagation rules

Non-null is a server guarantee. If a field is declared Non-null yet its resolver returns `null`, or field execution throws an error leaving the field without a value, GraphQL records an error and replaces the field's value with `null` at the nearest nullable ancestor. If the parent field is also Non-null, `null` keeps propagating upward. This rule is commonly called *null bubbling*.

Consider the schema:

```graphql
type Query {
    product: Product!
    status: String
}

type Product {
    id: ID!
    name: String!
    description: String
}
```

If the resolver for `Product.name` returns `null`, the `name` field violates the contract. Because `name` is Non-null, the `Product` object cannot be returned intact and is replaced by `null`. `Query.product` is also Non-null, so `null` keeps propagating up to the root. The response might look like:

```json
{
  "errors": [
    {
      "message": "Cannot return null for non-nullable field Product.name.",
      "path": ["product", "name"]
    }
  ],
  "data": null
}
```

The error message above is illustrative; exact text depends on the runtime and how the application handles exceptions. The key point is that `data` can become `null` because a violation on a Non-null field propagated through Non-null parent fields.

If you declare `product: Product` (nullable) instead of `product: Product!`, propagation stops at `product`. Other root fields such as `status` can still be returned:

```json
{
  "errors": [
    {
      "message": "A product field could not be completed.",
      "path": ["product", "name"]
    }
  ],
  "data": {
    "product": null,
    "status": "available"
  }
}
```

The error message in this example is also illustrative. GraphQL still returns data branches unaffected by the error.

### Null propagation in lists

The same rules apply to list elements:

- With `[Product]`, a `null` element is accepted; the list can still be returned.
- With `[Product!]`, if an element is `null`, the entire list becomes `null`. Because the list itself is nullable, propagation stops at the list.
- With `[Product!]!`, a `null` element turns the list into `null`, which then violates the list's own Non-null constraint and keeps propagating to the parent field.
- With `[Product]!`, the list cannot be `null`, but individual elements can still be `null`.

For example, if the schema declares `products: [Product!]!` and the second element fails to resolve, GraphQL does not replace only that element with `null`; the entire `products` field becomes `null`, and propagation continues according to the parent field's nullability.

## 4. Non-null in Inputs, Arguments, and Mutations

Non-null also applies to data sent by the client to the server. Example:

```graphql
type Mutation {
    createProduct(input: ProductInput!): Product!
}

input ProductInput {
    name: String!
    description: String
    tags: [String!]!
}
```

In this declaration:

- `input` is a required argument; clients cannot omit it or pass `null`.
- `name` is a required field in the input object.
- `description` may be omitted or passed as `null`.
- `tags` must provide a list and elements in the list cannot be `null`; an empty list is still valid.
- The `Product!` return type guarantees the mutation returns a non-`null` `Product` upon successful execution.

Valid mutation example:

```graphql
mutation {
    createProduct(input: {
        name: "Keyboard"
        description: "Wireless keyboard"
        tags: ["computer", "accessory"]
    }) {
        id
        name
    }
}
```

If the client omits `name`, omits `input`, or passes `null` for a Non-null position without a default value, GraphQL rejects the request during input validation/coercion and the mutation resolver is not invoked for that invalid request.

There is a distinction to note: omitting a nullable value and explicitly passing `null` are two different input states. Furthermore, if a Non-null argument or input field declares a default value, the client may omit that value and GraphQL uses the default. An explicit `null` value remains invalid for Non-null.

## 5. Mapping Non-null with resolvers in Spring for GraphQL

Spring for GraphQL typically uses SDL to define the schema and annotations like `@QueryMapping`, `@MutationMapping`, and `@SchemaMapping` to bind fields to Java methods.

Schema example:

```graphql
type Query {
    product(id: ID!): Product
}

type Product {
    id: ID!
    name: String!
    description: String
}
```

Corresponding resolver:

```java
@Controller
class ProductController {

    private final ProductService productService;

    ProductController(ProductService productService) {
        this.productService = productService;
    }

    @QueryMapping
    Product product(@Argument String id) {
        return productService.findById(id);
    }
}
```

Here the `id: ID!` argument requires the client to supply a GraphQL-valid ID. The `product: Product` field allows the resolver to return `null`, such as when the product is not found. If the schema is changed to `product(id: ID!): Product!`, a not-found case where the resolver returns `null` becomes a Non-null execution error and triggers null propagation.

Java annotations like `@Nullable` or `@NonNull` help IDEs, static analysis tools, and developers understand code intent. However, with schema-first development using SDL, the `!` symbol in the schema is the GraphQL declaration that determines API nullability. Do not assume changing Java annotations automatically updates SDL.

This also applies to asynchronous return types. If a resolver returns a publisher that emits no value, such as an empty-completing `Mono`, GraphQL treats the result as `null` for that field. If the field is Non-null, the application triggers the same error and null propagation rules as any other case.

## 6. Choosing between nullable and Non-null

Choose nullability based on the data guarantees the API can uphold, not solely on whether the current database table has a `NOT NULL` column.

| Case | Usually appropriate design | Reason |
|---|---|---|
| ID always exists for a valid object | `ID!` | Clients need a stable identifier. |
| Display name is always present when object is returned | `String!` | Server guarantees a name. |
| Product description might not be entered yet | `String` | `null` is a valid state for the data. |
| A collection can always be returned, even if empty | `[Item!]!` | Clients receive a list, possibly empty. |
| Relationship might not exist yet | `RelatedItem` | Avoids forcing clients to assume the relation always has data. |
| Argument required to perform an operation | `ID!` or `Input!` | GraphQL rejects requests missing required input. |

Practical guidelines:

1. Declare Non-null only when the server can guarantee the value in all normal execution scenarios.
2. Use nullable for data that can genuinely be absent, such as optional relationships or unprovided details.
3. For collections, consider `[Item!]!` if you want clients to always handle a list, even when empty.
4. Assess the blast radius of null bubbling. A deep Non-null field can wipe out parent data if parent levels are also Non-null.
5. When changing nullable to Non-null, audit legacy data, resolvers, external data sources, and existing schema consumers.

Non-null does not replace database constraints, Bean Validation, or business checks. For instance, `price: Float!` does not ensure price is greater than or equal to 0; `email: String!` does not validate email format.

## 7. Common mistakes

**Declaring `String!` when the resolver can return `null`.** Decide whether missing data is valid or an error. If valid, consider changing SDL to nullable. If invalid, ensure the service/resolver handles the condition without violating the contract.

**Assuming `[Item!]!` requires the list to be non-empty.** This syntax still allows `[]`. To enforce element count bounds, add separate validation.

**Confusing list nullability with element nullability.** Read from inside out: `!` immediately after the item type constrains each element; `!` after `]` constrains the list itself.

**Marking every field Non-null to make the schema look strict.** This can cause a single child-field error to erase an entire object or larger data branch due to null bubbling. Only commit to what the server actually guarantees.

**Thinking `!` validates business content.** `String!` can still be an empty string, and `Int!` can still be negative. Use validation for those rules.

**Testing only the schema without testing resolvers.** SDL can be valid while a resolver still returns `null` or throws at runtime. Test real requests and responses too.

## 8. Testing Non-null contracts

When testing a Spring for GraphQL API, cover both success cases and contract violations:

- For Non-null fields with data, verify the response contains a value of the right type.
- For nullable fields without data, verify the response contains `null` without raising a nullability error.
- For Non-null fields whose resolver returns `null` or errors out, verify the response includes `errors` and `data` is nulled at the exact level predicted by propagation rules.
- For missing or explicitly `null` Non-null arguments or input fields, verify the request is rejected and the mutation resolver does not execute.
- For lists, test empty lists, permitted null elements, and forbidden null elements separately according to each SDL declaration.

Spring for GraphQL's `GraphQlTester` can send documents and assert both data branches and errors in the response. These tests catch cases where the schema's nullability changed but resolvers or real data do not yet satisfy the new contract.

## Conclusion

Non-null types use `!` to make nullability an explicit part of the GraphQL contract. They apply to output fields, lists, individual list elements, arguments, and input fields. When designing SDL, identify which data is truly required, understand the effects of null bubbling, and ensure Spring resolvers uphold the guarantees published to clients.
