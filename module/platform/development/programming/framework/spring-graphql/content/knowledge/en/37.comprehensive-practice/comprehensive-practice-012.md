# Designing Schema Evolution

A GraphQL API is often consumed by multiple application versions at the same time. Web applications can be updated immediately, while older mobile apps continue sending operations shipped months earlier. Therefore, a schema must evolve in a way that preserves the contract existing clients rely on while paving the way for new capabilities.

With Spring for GraphQL, the SDL schema and Java resolvers together form that contract. A schema change is only complete when new fields have accurate resolvers, appropriate permissions, acceptable performance, and old operations continue to work as expected.

After this hands-on practice, you will be able to:

- Distinguish compatible changes, risky changes, and breaking changes.
- Extend a schema with optional fields, arguments, and input fields.
- Rename fields using a deprecate-then-migrate workflow.
- Maintain compatibility when evolving pagination, enums, and input objects.
- Implement resolvers using `@QueryMapping`, `@SchemaMapping`, and `@BatchMapping`.
- Verify schemas and operations with `GraphQlTester`, then roll out changes in stages.

## 1. Treating the Schema as a Public Contract

A GraphQL schema describes what clients are allowed to ask for and send to the server: data types, fields, arguments, inputs, enums, and nullability. Clients frequently generate code or validate operations against the schema, so a change can affect clients even when the server-side Java code compiles cleanly.

For example, a product catalog API initially exposes this schema:

```graphql
scalar BigDecimal

type Query {
    product(id: ID!): Product
    products: [Product!]!
}

type Product {
    id: ID!
    code: String!
    name: String!
    price: Money!
}

type Money {
    amount: BigDecimal!
    currency: String!
}
```

Clients may currently be calling:

```graphql
query ProductList {
    products {
        id
        code
        name
        price {
            amount
            currency
        }
    }
}
```

Already-released clients depend on the names `products`, `code`, the shape of `Money`, and nullability rules. When designing changes, start by identifying which operations use the affected parts of the schema. Operation logs, persisted queries, field usage metrics, or client inventories are useful sources for determining impact.

## 2. Classifying Compatibility Before Editing the Schema

Not every additive change is safe for every client. The following table serves as a practical guide for evaluating a release beforehand.

| Change | Typical Assessment | Reason to Consider |
|---|---|---|
| Adding a new Query or Mutation | Compatible | Old operations do not need to call the new field |
| Adding a new output field | Compatible | Old clients do not select that field; the new resolver must still work properly |
| Adding an optional argument | Compatible | Old clients can continue omitting the argument |
| Adding an optional input field | Compatible | Existing input objects remain valid |
| Marking an old field `@deprecated` | Compatible | The field still exists and continues serving old clients |
| Removing or renaming a field/argument | Breaking | Old operations may become invalid |
| Changing a return type or nullability | Potentially breaking | Generated code types and data-handling logic can change |
| Adding a required input field or argument | Breaking | Old requests do not send the required value |
| Removing an enum value | Breaking | Clients may still send or handle that value |
| Changing a field's meaning while keeping its name and type | Semantic contract break | Operations still run, but results no longer match client expectations |

In particular, evaluate nullability on both sides:

- For outputs, `Product` and `Product!` represent different guarantees. If a resolver returns `null` for a `!` field, GraphQL raises an execution error and the null value can bubble up to parent fields per null bubbling rules. Nullability changes must therefore be treated as contract changes and verified against real data.
- For inputs, `String` lets clients omit the field or send `null`; `String!` requires a valid value. Turning an optional input into a required one can break old requests.
- `0`, an empty string, and `null` are distinct values. Do not use `null` as a substitute for a default value if that alters business semantics.

## 3. Extending Additively

The safe rule is to add new capabilities first, give clients time to transition, and only then consider removing old capabilities. Prefer:

1. Adding new fields with clear names and meanings.
2. Adding optional arguments or optional input fields when filtering is needed.
3. Keeping old fields working while clients migrate.
4. Removing old fields only after usage drops to an acceptable level and deprecation notices follow your API policy.

Avoid changing the meaning of an existing field just to avoid adding a new name. For example, if `price` previously meant list price and now you need discounted price, add a field whose name clearly expresses the new concept or introduce a new type. Keeping the same name while changing its meaning causes silent bugs that are even harder for clients to detect than validation errors.

## 4. Practicing Schema Evolution from v1 to v2

Suppose the system needs three new capabilities: filtered and paginated search, renaming `code` to `sku`, and exposing stock and supplier details. We will extend the schema while keeping old operations intact.

The extended SDL can look like this:

```graphql
scalar BigDecimal

type Query {
    product(id: ID!): Product
    products: [Product!]!

    productConnection(
        filter: ProductFilter
        first: Int = 20
        after: String
    ): ProductConnection!
}

type Product {
    id: ID!
    code: String! @deprecated(reason: "Use sku instead.")
    sku: String!
    name: String!
    price: Money!
    stock: Int
    supplier: Supplier
}

type Money {
    amount: BigDecimal!
    currency: String!
}

input ProductFilter {
    categoryId: ID
    status: ProductStatus
}

enum ProductStatus {
    ACTIVE
    DRAFT
    ARCHIVED
}

type ProductConnection {
    edges: [ProductEdge!]!
    pageInfo: PageInfo!
}

type ProductEdge {
    cursor: String!
    node: Product!
}

type PageInfo {
    hasNextPage: Boolean!
    endCursor: String
}

type Supplier {
    id: ID!
    name: String!
}
```

Compatibility aspects in this example:

- `products` keeps its name and return type. Old clients continue working.
- `productConnection` is a new field. New clients can use `filter`, `first`, and `after`; all three arguments are optional.
- `ProductFilter` is newly added. Its input fields are optional so clients only need to send the filters they want.
- `code` remains present but is marked `@deprecated`. `sku` is the new field that new clients can select independently.
- `stock` and `supplier` are nullable because the data may not exist yet, may not be permitted to view, or may be absent from the data source for a specific product. Define each case clearly in the business layer and error handling.
- `BigDecimal` is a custom scalar; the application must register the corresponding runtime scalar so the SDL and GraphQL runtime agree on the same decimal format. Do not use `Float` for monetary values when the system requires decimal precision.

Old clients continue running old queries. New clients can send:

```graphql
query ProductSearch {
    productConnection(
        filter: { categoryId: "cat-10", status: ACTIVE }
        first: 20
    ) {
        edges {
            cursor
            node {
                id
                sku
                name
                stock
                supplier {
                    id
                    name
                }
            }
        }
        pageInfo {
            hasNextPage
            endCursor
        }
    }
}
```

Do not change the return type of `products` from `[Product!]!` to `ProductConnection!` in the same release. Those two types have different shapes. Creating a new field for the connection gives clients time to migrate without breaking existing operations.

## 5. Renaming Fields via Deprecation

GraphQL has no atomic field rename that keeps old operations automatically valid. Treat renaming as a multi-release process:

1. Add the new field, e.g., `sku`, and implement a resolver returning the same business value as `code`.
2. Keep `code` and annotate it with `@deprecated(reason: "Use sku instead.")`.
3. Update documentation, examples, and clients to use `sku`.
4. Track usage frequency of `code` per operation or client.
5. Remove `code` only in an announced breaking release coordinated with any remaining clients.

The `@deprecated` directive surfaces the replacement intent in schema introspection and developer tools. It does not automatically block requests, rewrite queries, or remove resolvers. During the transition period, the server must continue serving the old field.

## 6. Updating Resolvers in Spring for GraphQL

In a Spring Boot application using Spring for GraphQL, SDL files are typically placed under `src/main/resources/graphql/`. Spring builds the schema from these files and binds fields to the corresponding controller methods or data fetchers.

Example controller for the new Queries and backward-compatible fields:

```java
@Controller
public class ProductGraphQlController {

    private final ProductService productService;

    public ProductGraphQlController(ProductService productService) {
        this.productService = productService;
    }

    @QueryMapping
    public Product product(@Argument String id) {
        return productService.findById(id);
    }

    @QueryMapping
    public List<Product> products() {
        return productService.findAll();
    }

    @QueryMapping
    public ProductConnection productConnection(
            @Argument ProductFilter filter,
            @Argument Integer first,
            @Argument String after) {

        int pageSize = first == null ? 20 : Math.min(Math.max(first, 1), 100);
        return productService.findConnection(filter, pageSize, after);
    }

    @SchemaMapping(typeName = "Product", field = "code")
    public String legacyCode(Product product) {
        return product.sku();
    }
}
```

`@QueryMapping` binds a method to a field on `Query`. `@SchemaMapping` binds a method to a specific field on an object type. In the example, `code` can still be read from the new model via the compatibility resolver, while `sku` can be resolved by Spring from `Product`'s corresponding property/accessor if no custom logic is needed.

Capping `first` on the server prevents clients from requesting an excessively large page. Defaults in the SDL and limits in resolvers must stay aligned with the service's pagination policy. In a real API, the service must also validate cursors, enforce stable sort ordering, and check per-record access permissions.

## 7. Evaluating Input Objects When the Schema Changes

Adding optional fields to an input object is normally compatible:

```graphql
input ProductFilter {
    categoryId: ID
    status: ProductStatus
    minPrice: BigDecimal
    maxPrice: BigDecimal
}
```

Old clients that only pass `categoryId` remain valid. However, keep the meaning of fields stable. If `minPrice` and `maxPrice` are evaluated in the product's currency, document that clearly or include currency in the input; do not leave clients guessing.

For update mutations, distinguish three states: field omitted, field sent as `null`, and field sent with a concrete value. For example, omitting `description` may mean leaving the description unchanged, whereas sending `description: null` may mean clearing it. Plain Java DTOs sometimes lose this distinction when binding inputs. Spring for GraphQL provides `ArgumentValue<T>` to represent both omitted state and supplied values including `null`; use it when business logic must distinguish between the two.

Do not add a required input field to a mutation already in wide use if existing clients cannot send that field. You can create a new mutation with a new input type, or add an optional field and validate it under compatibility rules during the transition period.

## 8. Evolving Enums and Abstract Types

Enums are also part of the contract. Adding an enum value to an input-only enum generally lets the server accept a new option. However, when an enum appears in output, clients may generate code with exhaustive switch statements or assume only known values exist. Clients should include a fallback branch for unrecognized values.

Do not remove an enum value while data or clients still send that value. You can mark the old enum value `@deprecated` to announce the replacement, then measure usage before removing it.

For interfaces and unions, adding a new implementing type or union member can also affect clients using type-specific fragments. Clients must handle new `__typename` values. When extending abstract types, test operations using inline fragments and inspect clients that branch on `__typename`.

## 9. Keeping Pagination and Scalar Semantics Stable

Pagination is a classic example of a seemingly small change that directly impacts clients. When adding a connection, clearly specify:

- `first` is the maximum item count, with an explicit upper bound.
- `after` is an opaque server-generated cursor; clients must not parse its internal structure.
- Sort order must be deterministic across pages, even when multiple records share the same primary sort value.
- `hasNextPage` reflects remaining data under the exact same filter and access rules.
- `endCursor` can be `null` when there is no final edge.

For custom scalars such as `BigDecimal`, `DateTime`, or `Currency`, the schema must be accompanied by serialization, input parsing, and validation rules. Never switch format from a decimal string to a floating-point number merely because an internal Java type changed. If a new representation is needed, consider a new scalar or field and give clients time to migrate.

## 10. Security When Adding Fields

A new field can expose sensitive data that the parent Query did not previously provide. Access permissions must be evaluated at the appropriate field and record levels. For example, `stock` might be restricted to users with inventory permissions while `name` remains public.

With Spring Security, you can apply method security to resolvers, for instance:

```java
@PreAuthorize("hasAuthority('inventory:read')")
@SchemaMapping(typeName = "Product", field = "stock")
public Integer stock(Product product) {
    return inventoryService.availableStock(product.id());
}
```

Ensure method security is enabled in the application. Explicitly define behavior when a user lacks permission: return a GraphQL error for the field, return `null` under public policy, or reject the entire operation. Because `stock` is nullable in the SDL, an error or missing value on this field does not have to wipe out the entire `Product` object. Still, nullability does not replace access control; the resolver must still enforce permissions.

Beyond field-level permissions, lookups by `id`, filters, and cursors must enforce record-level authorization. Never allow a new field to accidentally bypass tenant boundaries or service-layer authorization conditions.

## 11. Controlling N+1 When Adding Relationships

Adding a `supplier` field can cause each `Product` to issue a separate query to load its supplier. With large lists, the schema remains valid, yet query cost scales linearly with product count. Spring for GraphQL supports `@BatchMapping` to load relationships in batches:

```java
@BatchMapping(typeName = "Product", field = "supplier")
public Map<Product, Supplier> supplier(List<Product> products) {
    return supplierService.findForProducts(products);
}
```

`findForProducts` should return a mapping from each source `Product` to its corresponding `Supplier`, honoring the field's semantics. If no relationship exists, handle it according to declared nullability. For more complex relationships, you can use `DataLoader` to batch requests and share results within the execution scope.

When adding new fields, check repository/service call counts, batch sizes, page limits, and nested query possibilities. GraphQL lets clients select many data branches in one operation; therefore, apply depth, complexity, or query cost limits according to application policy where appropriate.

## 12. Testing Old and New Operations with GraphQlTester

Testing schema creation only confirms the schema builds; it does not prove resolvers return accurate data. Keep representative operations for old clients and add new operations to your test suite.

Example with `GraphQlTester`:

```java
@SpringBootTest
class ProductGraphQlCompatibilityTests {

    @Autowired
    private GraphQlTester graphQlTester;

    @Test
    void oldFieldCodeRemainsAvailable() {
        graphQlTester.document("""
                query {
                    product(id: "p-1") {
                        id
                        code
                        sku
                    }
                }
                """)
            .execute()
            .path("product.code").entity(String.class).isEqualTo("SKU-001")
            .path("product.sku").entity(String.class).isEqualTo("SKU-001");
    }

    @Test
    void newConnectionSupportsOptionalFilterAndPagination() {
        graphQlTester.document("""
                query {
                    productConnection(
                        filter: { status: ACTIVE }
                        first: 10
                    ) {
                        edges { cursor node { id sku } }
                        pageInfo { hasNextPage endCursor }
                    }
                }
                """)
            .execute()
            .path("productConnection.edges").entityList(Object.class).hasSize(1);
    }
}
```

This is an illustrative test skeleton; fixtures, mocks, or test data must provide product `p-1` and the corresponding connection results. If using `@SpringBootTest`, the test setup must initialize all services and the GraphQL schema. You can use `@GraphQlTest` when you only want to test the controller slice and provide mocked dependencies.

You should also add checks for:

- Schema builds cleanly and custom scalars are registered.
- Deprecated fields remain queryable during the deprecation window.
- Clients can omit all optional inputs or supply only a subset.
- Omitted inputs are distinguished from `null` inputs when business logic requires it.
- Unauthorized users cannot read sensitive fields.
- Relationship fields do not introduce N+1 queries on list queries.
- Invalid cursors, oversized pages, and empty datasets behave according to contract.

## 13. Integrating Compatibility Checks into the Release Process

For every schema change, reviews should answer: which fields or arguments are added, changed, or removed; which operations use them; whether old clients remain valid; whether resolvers enforce proper data and permissions; and whether query costs change.

You can automate this by storing the previous release's schema and comparing it against the candidate schema in CI. Schema diff tools detect removed fields, changed types, new required inputs, or removed enum values. After diffing, validate real operations or persisted queries against the new schema to catch operations that would break.

Schema diffs do not catch every semantic change. For instance, keeping `price: Money!` while changing the default currency or price calculation logic can still break clients. Therefore, business tests, field description reviews, and runtime data monitoring remain essential.

## 14. Rolling Out via Expand–Migrate–Contract

Renaming `code` to `sku` can be shipped in the following sequence:

| Phase | Server-Side Changes | Client-Side Actions |
|---|---|---|
| Expand | Add `sku`, keep `code`, implement both resolvers | No immediate change required |
| Migrate | Keep both fields and monitor usage | Update queries, generated code, and tests to `sku` |
| Verify | Check logs confirming key clients no longer call `code` | Release updated clients |
| Contract | Remove `code` in an announced breaking change release | Confirm no clients depend on the old field |

When multiple server instances run concurrently during deployment, each instance must understand schemas and operations compatibly throughout the transition. Deploy resolvers supporting new fields before releasing clients that request them. Never delete an old field merely because a new client was published; base removal on observed usage and the agreed support lifecycle.

## 15. Pre-Merge Checklist for Schema Changes

- [ ] Affected existing operations, clients, and fields have been identified.
- [ ] Changes are classified as compatible, risky, or breaking.
- [ ] New fields have names, descriptions, types, and nullability matching business rules.
- [ ] New arguments and input fields are optional if old clients must keep sending old requests.
- [ ] Fields or enum values slated for replacement are marked `@deprecated` with a clear reason.
- [ ] Spring for GraphQL resolvers are implemented and handle missing data.
- [ ] Permissions are checked at both field and record levels.
- [ ] New relationship fields have been evaluated for N+1 and use batching/DataLoader as needed.
- [ ] Pagination, scalars, enums, and `null` semantics are documented consistently.
- [ ] `GraphQlTester` verifies both old and new operations.
- [ ] Schema diff and operation validation run in CI.
- [ ] A migration plan, usage tracking, and contraction timeline for old fields are in place.

## Practice Exercise

An order management API currently has `order(id: ID!): Order` and `Order.total: BigDecimal!`. The product needs to add payment status, currency details, and the ability to filter orders by a date range.

Design a schema evolution meeting these requirements:

1. Keep existing operations querying `order` and `total` working.
2. Add currency details without changing the meaning of `total`.
3. Add optional filtering to the order list query.
4. Mark an old field needing replacement with `@deprecated` and describe the client migration path.
5. Determine which fields must be nullable and which can guarantee non-null, with justification.
6. Write the new SDL, Spring for GraphQL resolvers, and at least two `GraphQlTester` tests: one for the old operation and one for the new operation.
7. If payment status is restricted to a specific user group, specify where permissions are checked and how errors are returned.

Once completed, verify for yourself that old clients can still send their original operations, new clients can use the new fields, and old field removal occurs only after reliable usage data confirms migration.
