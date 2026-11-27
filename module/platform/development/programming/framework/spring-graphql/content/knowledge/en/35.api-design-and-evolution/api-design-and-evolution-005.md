# Adding Fields Without Breaking Clients

GraphQL APIs are typically evolved by adding capabilities to the active schema rather than creating a new endpoint version for every change. Because clients only receive the fields selected in their operations, adding a new field to an object type usually does not invalidate existing queries. Older clients keep requesting the fields they know; newer clients can select the additional field when ready.

In Spring for GraphQL, this change must be made in sync across both the SDL and the data-handling layer. Adding a field to the schema without an appropriate resolver or data source can cause newer clients to receive `null`, execution errors, or incorrect results. A safe additive change preserves the old contract, defines clear semantics for existing data, and is tested against operations representing current clients.

## 1. Why can a GraphQL API evolve without versioning every change?

In REST, an endpoint typically returns a server-defined response structure. If the server adds a property to the JSON, clients using strict deserializers can run into issues depending on their technology stack. GraphQL works differently: clients declare the exact fields they need in the query.

For example, an older client sends:

```graphql
query ProductCard {
    product(id: "p-101") {
        id
        name
        price
    }
}
```

The server returns only the selected fields. When `brandLabel` is added to the schema, the operation above remains valid because it does not reference the new field and all old fields remain intact.

A newer client can request the extra field:

```graphql
query ProductCard {
    product(id: "p-101") {
        id
        name
        price
        brandLabel
    }
}
```

Both clients share the same endpoint and current schema. Older clients do not have to upgrade immediately when the server adds the field.

## 2. Additive changes vs. breaking changes

Additive changes extend the schema without invalidating currently valid operations. Breaking changes invalidate existing operations or alter semantics in a way current clients cannot safely handle.

| Change | Typical assessment | Reason |
|---|---|---|
| Adding a nullable field to an object type | Additive | Old queries do not need to select the new field. |
| Adding a new query or mutation | Additive | Old operations are unaffected. |
| Adding an argument with a default or nullable type | Additive | Older clients can continue omitting the argument. |
| Adding an optional field to an input object | Usually additive | Old inputs remain valid if the new field is not required. |
| Adding a non-null field to an output type | Validation-additive, requires data check | Resolver must guarantee a value whenever clients select the field. |
| Adding a required non-null argument without a default to an old field | Breaking | Old queries omitting the new argument become invalid. |
| Removing or renaming a field | Breaking | Old queries reference a field that no longer exists. |
| Changing a field's type or output nullability | Breaking/high risk | Data type or nullability contract changes. |
| Adding an enum value or union member | Potentially dangerous | Clients with exhaustive switch statements may not recognize the new value. |

Do not rely solely on a schema diff tool's "non-breaking" label. Consider GraphQL server validation, client code generation, how clients handle unknown values, and runtime resolver behavior.

## 3. Adding a field to an object type

Suppose the initial schema has `Product`:

```graphql
type Query {
    product(id: ID!): Product
}

type Product {
    id: ID!
    name: String!
    price: Float!
}
```

We want to add a brand label so clients can display it on a product card. We can add a nullable field:

```graphql
type Product {
    id: ID!
    name: String!
    price: Float!
    brandLabel: String
}
```

Older clients only select `id`, `name`, and `price`, so they are not forced to change. Newer clients select `brandLabel` when the UI needs it.

A nullable field fits when historical records lack a brand, records have not been enriched yet, or the resolver might not find a label. If the field truly always has a value for every existing `Product`, you can consider `String!`; however, you must guarantee that invariant in both the data and the resolver before publishing.

## 4. Why should new fields usually be nullable at first?

GraphQL nullability is part of the API contract:

- `String` allows the resolver to return a string or `null`.
- `String!` promises the resolver returns a string and never `null`.

If a `String!` field's resolver returns `null`, GraphQL raises an execution error and null can propagate up to the parent according to non-null propagation rules. This can wipe out the entire object or a larger portion of the response than the new field.

For instance, legacy records might not store `brandLabel`. If you declare:

```graphql
type Product {
    id: ID!
    brandLabel: String!
}
```

then the resolver must be able to compute a label for every `Product` clients can query, including legacy data. If that cannot be guaranteed, the schema should use `brandLabel: String` and clients should handle the absent-label case.

Nullable does not mean returning null arbitrarily. The contract should clearly explain whether null means "no data," "not applicable," or "unable to display." If multiple states need to be distinguished, consider a result object with `status`, `value`, or `reason` rather than using null for every scenario.

## 5. Older clients do not automatically receive new fields

GraphQL does not automatically include all fields in a response. Clients only receive the new field if their operation selects it.

Old query:

```graphql
query {
    product(id: "p-101") {
        id
        name
    }
}
```

The response retains the same shape:

```json
{
  "data": {
    "product": {
      "id": "p-101",
      "name": "Mechanical Keyboard"
    }
  }
}
```

New query:

```graphql
query {
    product(id: "p-101") {
        id
        name
        brandLabel
    }
}
```

The response includes `brandLabel` because the client requested it:

```json
{
  "data": {
    "product": {
      "id": "p-101",
      "name": "Mechanical Keyboard",
      "brandLabel": "Northwind"
    }
  }
}
```

This is the core mechanism that enables adding fields to a GraphQL object type without altering responses for existing queries.

## 6. Implementing the new field in Spring for GraphQL

Spring for GraphQL typically uses a schema-first approach: SDL describes the contract, while annotated controllers provide `DataFetcher`s for fields requiring custom logic.

Place the SDL in resources, e.g. `src/main/resources/graphql/schema.graphqls`:

```graphql
type Query {
    product(id: ID!): Product
}

type Product {
    id: ID!
    name: String!
    brandLabel: String
}
```

The controller can map the query and the new field:

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
class ProductController {

    private final ProductCatalog products;
    private final BrandQueryService brands;

    ProductController(ProductCatalog products, BrandQueryService brands) {
        this.products = products;
        this.brands = brands;
    }

    @QueryMapping
    ProductView product(@Argument String id) {
        return products.findById(id).orElse(null);
    }

    @SchemaMapping(typeName = "Product", field = "brandLabel")
    String brandLabel(ProductView product) {
        if (product.brandId() == null) {
            return null;
        }

        return brands.displayName(product.brandId()).orElse(null);
    }
}
```

The models and services used in the example:

```java
import java.util.Optional;

public record ProductView(String id, String name, String brandId) {}

public interface ProductCatalog {
    Optional<ProductView> findById(String id);
}

public interface BrandQueryService {
    Optional<String> displayName(String brandId);
}
```

`@QueryMapping` maps `Query.product`. `@SchemaMapping` maps `Product.brandLabel` and receives the parent object `ProductView`. If the Java object already has a matching property and simply needs to read its value, GraphQL's default property data fetcher can read it without writing `@SchemaMapping`. For computed fields, relationship lookups, or fields needing explicit control, an explicit resolver makes data retrieval transparent.

## 7. Do not forget the resolver and data source

Adding SDL only exposes the field in the schema. It does not produce data on its own.

Before releasing a new field, check:

1. Does the field have the right name and type in SDL?
2. Is a resolver registered for the field if it needs custom handling?
3. Does the parent object have enough data to compute the field?
4. Might legacy records be missing a value?
5. When data is missing, does the resolver return `null`, a default value, or a business error?
6. Are access permissions consistent with related fields?
7. Does the resolver introduce N+1 queries when clients select the field on a list?

If the new field fetches from a relationship, consider `@BatchMapping` or a `DataLoader` when queries can return multiple parent objects. Even an additive field can spike database load if its resolver issues a separate query per object.

## 8. Adding fields to an input object

Input objects are used when clients pass data into queries or mutations:

```graphql
input ProductFilter {
    category: String
}

type Query {
    products(filter: ProductFilter): [Product!]!
}
```

You can add an optional field:

```graphql
input ProductFilter {
    category: String
    minPrice: Float
}
```

Older clients sending only `category` remain valid because `minPrice` can be omitted or passed as null. The resolver/service must clearly define how to behave when `minPrice` is not provided.

Do not add a non-null field without a default to an input object already in use:

```graphql
input ProductFilter {
    category: String
    minPrice: Float!
}
```

Existing requests that omit `minPrice` will become invalid. If the new field is mandatory for a new business flow, consider adding a new mutation or input type, or making the field nullable/defaulted and enforcing requiredness conditionally by context.

## 9. Adding optional arguments to an existing field

New arguments should be nullable or have a default value so existing operations stay valid.

Before:

```graphql
type Query {
    products: [Product!]!
}
```

After:

```graphql
type Query {
    products(category: String): [Product!]!
}
```

The old query `products { id name }` remains valid. New queries can filter by category:

```graphql
query {
    products(category: "hardware") {
        id
        name
    }
}
```

In Spring for GraphQL, the resolver can accept the argument:

```java
@QueryMapping
List<ProductView> products(@Argument String category) {
    return products.findByCategory(category);
}
```

If a stable default value is needed, declare the default in SDL:

```graphql
type Query {
    products(limit: Int = 20): [Product!]!
}
```

Do not add a required non-null argument to an existing field without a client migration plan:

```graphql
type Query {
    products(category: String!): [Product!]!
}
```

Existing operations omitting `category` will fail during validation before the resolver is ever invoked.

## 10. Be careful with new enum values

Adding an enum value does not invalidate old GraphQL queries at the schema level, but it can break older clients in their response-handling code.

Example:

```graphql
enum OrderStatus {
    PENDING
    PAID
    CANCELLED
}
```

Then adding:

```graphql
enum OrderStatus {
    PENDING
    PAID
    CANCELLED
    REFUNDED
}
```

Clients using exhaustive `switch` statements may lack a branch for `REFUNDED`. For enums returned to clients, include a fallback branch for unknown values:

```typescript
switch (order.status) {
  case "PENDING":
    return showPending();
  case "PAID":
    return showPaid();
  case "CANCELLED":
    return showCancelled();
  default:
    return showUnknownStatus();
}
```

The TypeScript snippet merely illustrates defensive client handling. For clients with generated types from the schema, configure and test how the code generator handles new enum values.

## 11. Be careful when extending interfaces or unions

Adding a new object type to a union or adding a new implementation to an interface can expose older clients to an unknown runtime type.

Union example:

```graphql
union SearchResult = Product | Brand
```

When adding `Article`:

```graphql
union SearchResult = Product | Brand | Article
```

Clients with fragments for `Product` and `Brand` stay valid, but result-handling code should include a fallback for an unknown `__typename`. Similarly, clients handling interfaces should avoid assuming only the concrete types known at build time exist.

## 12. Adding fields to an interface

If you add a field to a GraphQL interface, every object type implementing that interface must provide the corresponding field. This change can require updating multiple types and resolvers simultaneously.

Example:

```graphql
interface Node {
    id: ID!
}
```

If `createdAt` is added:

```graphql
interface Node {
    id: ID!
    createdAt: String
}
```

Object types such as `Product`, `Order`, and `Customer` that `implements Node` must declare `createdAt` with a compatible type. Before merging the change, verify all implementations and schema composition if using Federation.

When only one object type needs the new field, adding it directly to that object type has a smaller blast radius and fewer constraints.

## 13. Adding fields in a federated system

With GraphQL Federation, a new field must be added to the subgraph that owns it. If the new field sits on an entity shared across multiple subgraphs, verify keys, ownership, and composition.

For example, the Reviews subgraph adds `reviewCount` on `Product`:

```graphql
type Product @key(fields: "id") {
    id: ID!
    reviews: [Review!]!
    reviewCount: Int
}
```

The resolver can compute the review count:

```java
@SchemaMapping(typeName = "Product", field = "reviewCount")
Integer reviewCount(Product product) {
    return reviews.countByProductId(product.id());
}
```

Before releasing, verify:

- The new field is defined only in the subgraph that owns it, unless using appropriate shareable directives.
- Required entity keys are present in the representation so the subgraph can resolve the field.
- The subgraph has an `@EntityMapping` to resolve `Product`.
- Schema composition succeeds.
- The gateway/router is updated with the new supergraph artifact before clients send queries selecting the new field.
- The resolver has appropriate data access and performance.

Do not add the same field to multiple subgraphs expecting the gateway to pick a resolver automatically. Field ownership must be unambiguous or declared shareable in accordance with the Federation specification.

## 14. Marking the old field deprecated when replacing it

If a new field replaces an old field, keep the old field and mark it deprecated:

```graphql
type Product {
    id: ID!
    displayName: String
    name: String @deprecated(reason: "Use displayName instead.")
}
```

Older clients can still query `name`. Newer clients switch to `displayName`. Introspection and schema tools can display the deprecation reason to guide API consumers.

Deprecation is a migration signal, not an automatic mechanism blocking calls to the field. The server must keep serving the deprecated field until there is reliable evidence that required clients have stopped using it.

## 15. Workflow for migrating an old field to a new field

A safe workflow can be divided into stages:

1. **Add:** add the new field and resolver while keeping the old field intact.
2. **Test:** verify that both old and new queries work.
3. **Announce:** publish the new field, rationale, and migration examples.
4. **Migrate clients:** update individual applications or operations to the new field.
5. **Monitor:** check field usage, persisted operations, logs, and client versions.
6. **Deprecate:** mark the old field with a clear reason once the sunset phase begins.
7. **Remove:** only delete the old field after assessing impact and honoring client support policies.

Do not remove a field merely because it has been marked deprecated for a fixed duration. An infrequently used legacy client that remains business-critical may require a longer support window.

## 16. Testing to protect older clients

Schema diffs can detect certain breaking changes, but they do not replace runtime tests. With Spring for GraphQL, `GraphQlTester` can execute operations matching those used by clients.

Example test for old and new queries:

```java
import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.BDDMockito.given;

@GraphQlTest(ProductController.class)
class ProductControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    ProductCatalog products;

    @MockitoBean
    BrandQueryService brands;

    @Test
    void oldQueryStillWorksAfterAddingBrandLabel() {
        given(products.findById("p-101"))
            .willReturn(Optional.of(
                new ProductView("p-101", "Keyboard", "brand-1")
            ));

        graphQlTester.document("""
                query {
                    product(id: "p-101") {
                        id
                        name
                    }
                }
                """)
            .execute()
            .path("product.name")
            .entity(String.class)
            .isEqualTo("Keyboard");
    }

    @Test
    void newQueryCanReadBrandLabel() {
        given(products.findById("p-101"))
            .willReturn(Optional.of(
                new ProductView("p-101", "Keyboard", "brand-1")
            ));
        given(brands.displayName("brand-1"))
            .willReturn(Optional.of("Northwind"));

        graphQlTester.document("""
                query {
                    product(id: "p-101") {
                        id
                        brandLabel
                    }
                }
                """)
            .execute()
            .path("product.brandLabel")
            .entity(String.class)
            .isEqualTo("Northwind");
    }
}
```

This example uses `@GraphQlTest` from Spring Boot 3.x and `@MockitoBean` from Spring Framework 6.2 and later. In Spring Boot 4.x, `@GraphQlTest` moved to package `org.springframework.boot.graphql.test.autoconfigure`. On older Spring Framework versions, you can use `@MockBean` if supported by that Spring Boot version.

The first test is important because it proves existing operations stay valid after schema expansion. The second test proves the new field has a working resolver and real data. Add tests for the null `brandId` or missing brand cases to verify nullable field semantics.

## 17. Checking schema diffs in CI

Store SDL in version control and inspect schema changes on pull requests. Schema diffs can detect:

- Removed fields or types.
- Renamed fields or changed types.
- Output nullability changes.
- New arguments becoming required.
- Removed enum values.
- Changed directives or entity keys.
- Federation ownership changes that break composition.

With a schema registry, you can run schema checks against operation usage to determine whether changes affect active clients. Still, operation usage only reflects recorded traffic; account for offline clients, older mobile apps, batch jobs, and external partners.

CI should include at minimum:

1. Schema syntax/validation.
2. Schema compatibility diff.
3. Resolver unit tests.
4. GraphQL contract tests for legacy operations.
5. Integration tests for the new field and its data dependencies.
6. Federation composition tests if the module is a subgraph.

## 18. Tracking field usage

Before removing an old field, you need to know which clients still use it. Information can be collected at the gateway or via GraphQL instrumentation:

- Operation name and operation signature/hash.
- Fields selected in the operation.
- Invocation counts and execution timing.
- Client/application identity if a reliable identification mechanism exists.
- Application version or persisted operation identifier if sent by the client.

Avoid logging full variables or sensitive data solely to track usage. Metrics should use tags with controlled cardinality; never put raw user IDs or full query text in metric tags.

If field-level usage data is unavailable, use persisted operation registries, access logs, or gateway telemetry to estimate blast radius. You cannot conclude a field is unused merely because no requests appeared over a few days.

## 19. Adding new fields can impact performance

A new field does not automatically cause old queries to fetch extra data because GraphQL only executes selected fields. However, once new clients select that field, the resolver can increase database or external service calls.

Example list query:

```graphql
query {
    products {
        id
        name
        brandLabel
    }
}
```

If `brandLabel` queries the database once per `Product`, the query can trigger an N+1 problem. Use `@BatchMapping` or a `DataLoader` to batch brand IDs and load them together. Enforce pagination limits and monitor the new field's latency after release.

Do not perform external queries or expensive computations inside a resolver when the field has not been requested by the client. Resolvers only run when the field appears in the selection set, so preserve proper lazy execution.

## 20. Adding new fields can impact security

A new field may expose data that clients previously could not access. Check authorization at the field or application service level:

- Does the field contain sensitive or internal data?
- Is the user authorized to read this field on the specific resource?
- Are tenant/ownership checks enforced?
- When unauthorized, does the API return an error or null? Is that behavior consistent with current policy?
- Does the DataLoader scope caches per request and partition appropriately by security context?

Adding a field must never inadvertently broaden permissions for a query originally authorized only for older fields.

## 21. When a new field should not be added to an existing type

Sometimes a new field has completely different semantics or applies only in certain contexts. Consider:

- Creating a nested object type to group a set of related attributes.
- Adding a dedicated query tailored to the new use case.
- Creating a new input type if the mutation structure has changed substantially.
- Using an interface/union if the response genuinely has multiple variants.
- Keeping the old field and adding the new field during a migration period.

Do not cram unrelated fields onto an existing type merely to avoid introducing a new type. The schema should express the domain cleanly and remain evolvable.

## 22. Checklist before releasing a new field

- [ ] The new field has a clear name and semantics.
- [ ] Output field is nullable if existing data does not guarantee a value.
- [ ] New input fields or arguments are not required for older clients.
- [ ] The resolver or property fetcher returns accurate data.
- [ ] Null, not-found, and authorization semantics are clear.
- [ ] The field does not introduce N+1 queries or unbounded cost.
- [ ] Legacy queries still pass in contract tests.
- [ ] New queries return expected data in integration tests.
- [ ] Schema diff and Federation composition (if applicable) pass.
- [ ] API documentation and client examples are updated.
- [ ] Telemetry is sufficient to observe the field after release.

## 23. Common mistakes

**Adding a non-null field when legacy data has no value.** A resolver returning null causes an execution error and can propagate null to the parent. Use a nullable field or backfill data before promising non-null.

**Editing only the SDL without implementing a resolver.** The field appears in the schema but has no data. Verify property fetchers and `@SchemaMapping`.

**Adding a required argument to an existing field.** Older operations omitting the argument will fail validation. Use a nullable argument or one with a default value.

**Adding a required input field.** Older clients sending input objects without the new field become invalid. Start with an optional field or an appropriate default.

**Adding an enum value without preparing clients.** Exhaustive switch statements on clients may fail on the new value. Add fallback branches and test code generation.

**Adding a field to an interface and forgetting implementations.** Object types implementing the interface must be updated to fulfill the new contract.

**Deprecating and removing immediately.** Deprecation does not prove clients have migrated. Track usage and coordinate support windows.

**Skipping checks for new fields in Federation.** Composition or entity resolution can fail if ownership, keys, and resolvers are inconsistent.

**Ignoring resolver cost.** New fields can introduce N+1 queries, latency, or downstream load once clients begin selecting them.

## Conclusion

To add fields without breaking clients, extend the schema additively, keep existing fields intact, and choose nullability matching actual data. In Spring for GraphQL, update SDL alongside resolvers, test both legacy and new operations with `GraphQlTester`, check schema diffs in CI, and monitor performance and usage after release. Changes involving required inputs, required arguments, enums, interfaces, and unions require extra review because they can introduce compatibility risks even when they look like a single-line schema addition.

## References

- [GraphQL — Schema Design](https://graphql.org/learn/schema-design/)
- [GraphQL — Schema Change Management](https://www.graphql.org/learn/governance-versioning/)
- [GraphQL — Review and Validate Schema Changes](https://www.graphql.org/learn/schema-review/)
- [GraphQL Specification — Type System and `@deprecated`](https://spec.graphql.org/September2026/#sec--deprecated)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Apollo — Schema Basics and Schema Evolution](https://www.apollographql.com/docs/apollo-server/schema/schema)
