# Domain-Driven Schema Design

A GraphQL schema is the contract that clients use to read and mutate data. When designing a schema around the domain, types, fields, inputs, and mutations should express the business concepts supported by the system, rather than directly mirroring database tables or JPA entities.

In Spring for GraphQL, the SDL schema defines the contract; resolvers map fields to application services; and services execute use cases and call domain logic or repositories. This structure helps the API preserve the business language even when the database, ORM, or service implementation changes.

For example, an e-commerce system might have the Catalog, Ordering, and Customer domains. Catalog manages product information; Ordering manages shopping carts, orders, and order states; Customer manages customer profiles. A GraphQL schema can unify those concepts into an easy-to-use graph, while each field still needs a clear owner and semantics.

## 1. The schema is the contract between the domain and clients

A GraphQL schema answers three questions:

1. What business concepts can clients request?
2. What actions can clients perform?
3. What rules govern how data and errors are represented?

A schema is not a copy of the database. A `product` table may have dozens of technical columns such as `internal_status`, `created_by`, `row_version`, `deleted_at`, or `supplier_cost`. Clients should only see fields that are meaningful to their use cases and that they are authorized to access.

Similarly, a domain aggregate may consist of multiple internal entities, while the API only needs to return a read model suited to the screen. Conversely, a GraphQL type can aggregate data from multiple aggregates or services if that forms a coherent concept for clients.

| Component | Should reflect | Avoid directly mirroring |
| --- | --- | --- |
| GraphQL type | Business concept or read model | Table/ORM entity name |
| Field | Attribute or relationship meaningful to clients | Every database column |
| Query | Read need/use case | Repository method or SQL |
| Mutation | Business action | Generic insert/update/delete |
| Input type | Data needed to perform an action | Directly writable JPA entity |
| Error | Outcome or error per contract | Stack traces and internal exceptions |

A good schema helps clients understand the domain without needing to know where the system stores data or which service is handling it.

## 2. Start from bounded contexts

In Domain-Driven Design, a bounded context is the boundary within which a domain model and business language have consistent meaning. A word can carry different meanings across contexts.

For example, the word Product:

- In Catalog, Product is an item currently offered for sale, with a name, description, current price, and visibility status.
- In Ordering, an order line needs to store the name and unit price at the time of ordering so the invoice does not change when Catalog updates the product.
- In Shipping, Product may only need dimensions, weight, and packaging requirements.

Do not force all contexts to share a single Product object with every field. When semantics differ, express them explicitly with appropriate types, such as `Product`, `OrderLineProductSnapshot`, and `ShippableItem`.

A GraphQL schema can unify the querying experience without erasing bounded context distinctions. Sharing a single type name only makes sense when services truly share the same semantics and ownership is clearly defined.

## 3. Use ubiquitous language in types and fields

Ubiquitous language is the shared language between domain experts and the development team within a bounded context. Names of types, fields, enums, and mutations should use terms that the domain team understands and uses.

| Technical or vague name | Clearer domain-oriented name |
| --- | --- |
| statusCode | fulfillmentStatus or paymentStatus |
| process | placeOrder or cancelOrder |
| data | orderSummary or productDetails |
| userRef | customer |
| amount | total, unitPrice, or refundAmount |
| updateRecord | changeShippingAddress |

Avoid using a single `status` field for multiple concepts. An order may have `orderStatus`, `paymentStatus`, and `fulfillmentStatus`; they change according to different rules.

Field names should also describe stable semantics. If the `price` field is the current Catalog price, specify the currency and calculation rules. If the `total` field is the order total, clearly define whether it includes tax, shipping fees, and discounts.

## 4. Distinguish domain model, persistence model, and GraphQL model

These three models can be related without having to be identical:

| Model | Purpose | Example |
| --- | --- | --- |
| Domain model | Protect invariants and business rules | Order aggregate, OrderLine, Money |
| Persistence model | Store and query data | JPA entity, relation, index, join table |
| GraphQL model | Provide a contract for clients | Order, OrderItem, OrderConnection |

Example JPA entity:

~~~java
@Entity
public class OrderEntity {

    @Id
    private UUID id;

    private UUID customerId;
    private String internalState;
    private BigDecimal totalAmount;
    private String currencyCode;
    private long version;
    private Instant createdAt;

    // JPA relationships and persistence details
}
~~~

GraphQL can expose:

~~~graphql
type Order {
    id: ID!
    status: OrderStatus!
    total: Money!
    placedAt: DateTime!
    items: [OrderItem!]!
}
~~~

The GraphQL type does not need to expose `internalState`, `version`, or technical columns. The resolver/service maps from the domain or read model to the GraphQL response type.

If a JPA entity is returned directly, database mapping changes can accidentally alter the API, getters can trigger lazy loading, and default fields can leak data that should not be exposed. DTOs/read models provide better contract control.

## 5. Design the schema from use cases

Start with the questions clients need to answer, then identify which domain service owns the data:

- The catalog page needs to search and filter products.
- The detail page needs product information, price, and stock availability.
- The order page needs status, total amount, and line items.
- Buyers need to place an order, cancel an order, or change the shipping address under business conditions.

From there, create root queries:

~~~graphql
type Query {
    product(id: ID!): Product
    searchProducts(input: ProductSearchInput!): ProductConnection!
    order(id: ID!): Order
    myOrders(first: Int = 20, after: String): OrderConnection!
}
~~~

Query names express read needs in the domain language. There is no need to expose `findProductById`, `selectOrders`, or `getProductFromDatabase`. Naming can follow the project's conventions, but semantics must be clear.

A query can return a read model aggregated from multiple sources. For example, `orderDetails` can include order details, payment status, and shipping information. However, consider latency, field ownership, and the possibility of a dependency failing.

## 6. Design GraphQL types around business concepts

Example schema for Catalog and Ordering:

~~~graphql
scalar DateTime
scalar Decimal

type Product {
    id: ID!
    name: String!
    description: String
    price: Money!
    availability: ProductAvailability!
}

type Money {
    amount: Decimal!
    currency: CurrencyCode!
}

type Order {
    id: ID!
    status: OrderStatus!
    placedAt: DateTime!
    total: Money!
    items: [OrderItem!]!
}

type OrderItem {
    quantity: Int!
    unitPrice: Money!
    product: OrderLineProductSnapshot!
}

type OrderLineProductSnapshot {
    productId: ID!
    nameAtPurchase: String!
}

enum ProductAvailability {
    IN_STOCK
    OUT_OF_STOCK
    PREORDER
}

enum OrderStatus {
    PENDING
    CONFIRMED
    CANCELLED
    FULFILLED
}
enum CurrencyCode {
    VND
    USD
    EUR
}
~~~

The schema above distinguishes Catalog's current `Product` from the product name snapshot at the time of purchase. `OrderLineProductSnapshot` prevents order history from changing when `Product.name` is updated.

`Money` is a value object with `amount` and `currency` instead of returning a unitless `BigDecimal`. `Decimal` and `CurrencyCode` should be defined with scalars or enums appropriate for the contract; do not use `Float` for monetary calculations requiring decimal precision.

`DateTime` and `Decimal` are custom scalars in this example. Declaring a scalar in SDL is not enough to handle data; the application needs to register the corresponding `GraphQLScalarType`/`Coercing` via `RuntimeWiringConfigurer` or an appropriate wiring mechanism. `CurrencyCode` is an enum, so GraphQL Java can handle it as an enum once the type is declared.

## 7. Choose types and fields based on semantics

Type choices directly affect the contract:

- Use `ID` for identifiers that clients pass back; `ID` does not have to be a UUID.
- Use `enum` for finite sets of values with business meaning.
- Use `object type` for multi-component value objects.
- Use `input object` for sets of input data in queries/mutations.
- Use `connection` for large collections requiring pagination.
- Use `custom scalar` when there is a clear format and serialize/parse rules.

Do not use `String` for everything. A date/time, currency, status, or address field may need a more specific type to reduce ambiguity.

Custom scalars need consistent coercing logic, format, and validation between server and client. For example, `DateTime` should publish the timezone/offset and ISO-8601 format that the API accepts. Do not create a scalar merely to rename `String` if there are no additional semantics or validation.

## 8. Input types and output types should be separate

Inputs serve actions, and outputs describe states or results. Do not reuse a single type for both directions just because the fields overlap.

Example order placement input:

~~~graphql
input PlaceOrderInput {
    items: [PlaceOrderItemInput!]!
    shippingAddress: ShippingAddressInput!
    idempotencyKey: String!
}

input PlaceOrderItemInput {
    productId: ID!
    quantity: Int!
}

input ShippingAddressInput {
    recipientName: String!
    addressLine1: String!
    city: String!
    postalCode: String
    countryCode: String!
}
~~~

Inputs should only accept values that the caller is allowed to provide. Do not let clients send `total`, `orderStatus`, `createdAt`, `tenantId`, or `internalVersion` if those values are determined by the server/domain.

Output:

~~~graphql
type PlaceOrderPayload {
    order: Order
    userErrors: [UserError!]!
}

type UserError {
    code: String!
    message: String!
    field: String
}
~~~

Separating input and output allows the API to evolve independently. For example, the server can add a computed field to `Order` without turning it into a field that clients are allowed to write.

## 9. Mutations should express business actions

Mutations should describe commands or use cases, not just generic CRUD:

~~~graphql
type Mutation {
    placeOrder(input: PlaceOrderInput!): PlaceOrderPayload!
}
~~~

A `placeOrder` mutation may need to check:

1. Whether the Product is still available for sale.
2. Whether the quantity is valid.
3. Current prices and promotions.
4. Whether the customer is authorized to place the order.
5. Whether the shipping address is supported.
6. The invariants of the Order aggregate.

If the schema only has `updateOrder(id, fields)`, clients can send arbitrary statuses or create invalid state transitions. Action-oriented mutations help the domain enforce transitions and validation.

Mutation resolvers should call an application service/command handler. Do not write all order placement rules inside a controller or resolver.

## 10. Naming and organizing root fields

The Query root is the entry point for read use cases. The Mutation root is the entry point for commands. The Subscription root is the entry point for event streams if the domain has realtime needs.

Example of extending the root query:

~~~graphql
extend type Query {
    productsByCategory(categoryId: ID!, first: Int = 20): ProductConnection!
}
~~~

Root Query and Mutation were already declared in earlier sections; when splitting SDL across files, use `extend type` to add fields to an existing root type. Avoid creating overly generic root fields like `entity(type, id)` or `execute(command, payload)`. Those fields strip clients of type safety and push semantics into untyped JSON/strings without a clear schema.

There is no need to create a root field for every repository method. The API should only expose operations that provide value to clients.

## 11. Relationships between types and aggregate boundaries

An aggregate is a business consistency boundary. An aggregate root controls the invariants of the objects inside the aggregate.

A GraphQL object graph can be broader than an aggregate graph. For example, `Order` has `customer` and `product`; however, Customer, Product, and Order may belong to different aggregates or bounded contexts.

When resolving a relationship field:

- If the data resides in the same aggregate and is needed for the use case, the application service can load the same aggregate.
- If the data belongs to another aggregate in the same service, consider a query service or DataLoader.
- If the data belongs to another service, call the owner service's contract or use Federation.
- If the field requires historical data, store a snapshot/value object rather than querying the current value.

Do not create direct JPA relationships across services. GraphQL can represent relationships via IDs and resolvers, but persistence boundaries must still be preserved.

## 12. Do not turn GraphQL types into an unbounded object graph

A schema can create relationship cycles:

~~~graphql
type Customer {
    orders: [Order!]!
}

type Order {
    customer: Customer!
}
~~~

Type reference cycles are valid in GraphQL. However, queries can nest deeply:

~~~graphql
query {
    customer(id: "c-1") {
        orders {
            customer {
                orders {
                    customer {
                        id
                    }
                }
            }
        }
    }
}
~~~

Not every relationship in the domain needs to be exposed bidirectionally. You can expose only `Customer.orders` and `Order.customerSummary` if use cases require them. For large collections, use connections and cap page sizes.

Depth limits, complexity limits, and DataLoaders help control cost, but designing a schema with clear directionality is more important than exposing every relationship and trying to restrict it afterward.

## 13. Field ownership and resolver boundaries

Each field should have a clear data source and owner. For example:

| Field | Owner | Resolver/use case |
| --- | --- | --- |
| Product.name | Catalog | ProductQueryService |
| Product.price | Pricing/Catalog per domain model | PriceQueryService |
| Order.status | Ordering | OrderQueryService |
| Order.total | Ordering | Order total/read model |
| Order.customer | Customer or Order read model | CustomerClient/DataLoader |
| OrderItem.nameAtPurchase | Ordering | Snapshot within Order |

In a modular monolith, the owner can be an application module. In microservices, the owner is typically the service that owns the data. A resolver can call the owner service through an API client or DataLoader.

Do not let a field implicitly depend on a JPA entity getter if doing so causes uncontrolled queries. Explicit resolvers make it clear which service a field calls and allow independent instrumentation and testing.

## 14. Implementing thin resolvers in Spring for GraphQL

SDL defines fields; `@QueryMapping`, `@MutationMapping`, and `@SchemaMapping` map fields to Java methods.

~~~java
@Controller
public class ProductQueryController {

    private final ProductQueryService productQueryService;

    public ProductQueryController(ProductQueryService productQueryService) {
        this.productQueryService = productQueryService;
    }

    @QueryMapping
    public Product product(@Argument String id, Principal principal) {
        return productQueryService.findVisibleProduct(id, principal);
    }

    @QueryMapping
    public ProductConnection searchProducts(
            @Argument ProductSearchInput input,
            Principal principal) {
        return productQueryService.search(input, principal);
    }
}
~~~

The controller is responsible for binding and orchestration. `ProductQueryService` handles filtering, authorization, repositories/clients, and mapping to the GraphQL read model.

For mutations:

~~~java
@Controller
public class OrderMutationController {

    private final PlaceOrderUseCase placeOrderUseCase;

    public OrderMutationController(PlaceOrderUseCase placeOrderUseCase) {
        this.placeOrderUseCase = placeOrderUseCase;
    }

    @MutationMapping
    public PlaceOrderPayload placeOrder(
            @Argument PlaceOrderInput input,
            Principal principal) {
        return placeOrderUseCase.execute(input, principal);
    }
}
~~~

Resolvers should not open transactions themselves, mutate multiple entities, or call repositories directly when a use case has business rules. The application service owns the transaction boundary and invokes the domain model.

## 15. Using @SchemaMapping for meaningful relationships

A field does not necessarily need its own resolver if Spring GraphQL can read the property from the source object. However, when a field needs to call a service, enforce policy, or transform data, `@SchemaMapping` makes this explicit:

~~~java
@Controller
public class OrderFieldController {

    private final CustomerQueryService customerQueryService;

    public OrderFieldController(CustomerQueryService customerQueryService) {
        this.customerQueryService = customerQueryService;
    }

    @SchemaMapping(typeName = "Order", field = "customer")
    public CustomerSummary customer(Order order, Principal principal) {
        return customerQueryService.findVisibleSummary(
            order.customerId(), principal);
    }
}
~~~

If multiple `Order` instances need `Customer`, the resolver above can cause an N+1 problem. Use `@BatchMapping` or a `DataLoader` to batch customer IDs together. Batch loaders must enforce the same authorization scope and must not share caches across principals.

## 16. Domain schemas and read models

GraphQL often serves flexible queries, so the response model does not have to be the raw domain aggregate. You can build dedicated read models to return aggregated data:

~~~java
public record OrderSummary(
        String id,
        OrderStatus status,
        Money total,
        Instant placedAt,
        int itemCount) {
}
~~~

A read model can come from a projection, query service, or CQRS read store. It helps optimize screens without forcing the domain aggregate to match the exact structure GraphQL requires.

However, do not create a new read model for every minor selection set. Choose abstractions based on use cases, query cost, and reusability. For relationship fields requested independently, a DataLoader may be more suitable.

## 17. Designing nullability around invariants

The `!` in GraphQL SDL carries contract meaning:

- `String!` means the field always has a value when its parent is returned.
- `String` means the field may be null.
- `[Order!]!` means the list always exists and each element is non-null.
- `[Order]` allows both the list and individual elements to be null.

Only declare non-null when the domain or read model guarantees that invariant. For example, `Order.id` is typically non-null. An Order's `Customer` might no longer be visible due to a privacy policy or legacy data; if the API can return null, do not declare `Customer!` solely because the database relationship used to be mandatory.

Nullability also affects resolver failures. If a non-null field fails, GraphQL null propagation can turn its parent into null and bubble up higher. For fields backed by external services, consider partial failure and the client contract.

Do not use non-null as a way to force data to be present. Ensure the data and resolver genuinely uphold the contract.

## 18. Designing collections and pagination

Do not return unbounded collections for domains whose data can grow over time. For example, `myOrders` should have `first`/`after` and a connection:

~~~graphql
input ProductSearchInput {
    keyword: String
    availability: ProductAvailability
}

type ProductConnection {
    edges: [ProductEdge!]!
    pageInfo: PageInfo!
}

type ProductEdge {
    cursor: String!
    node: Product!
}

type OrderConnection {
    edges: [OrderEdge!]!
    pageInfo: PageInfo!
}

type OrderEdge {
    cursor: String!
    node: Order!
}

type PageInfo {
    hasNextPage: Boolean!
    hasPreviousPage: Boolean!
    startCursor: String
    endCursor: String
}
~~~

Pagination requires a stable sort order, cursors tied to the sort key and filters, a page size cap, and an authorization scope. For large datasets, keyset/cursor pagination is generally better suited than offset pagination at deep pages.

`totalCount` should only be provided when clients genuinely need it and the database can compute it at an acceptable cost. Do not run `COUNT(*)` just to determine whether there is a next page; querying `n + 1` items is usually sufficient.

## 19. Domain-aligned error contracts

Business errors and GraphQL execution errors need to be distinguished:

- Product does not exist: `NOT_FOUND` or `null` depending on the query contract.
- Not authorized to view Order: `FORBIDDEN` or concealing existence per policy.
- Invalid order quantity: validation error.
- Out of stock: can be a business outcome of `placeOrder`, not necessarily a system error.
- Database timeout: internal/dependency error, not `BAD_REQUEST`.

For mutations, business outcomes can be represented in the payload:

~~~graphql
type PlaceOrderPayload {
    order: Order
    userErrors: [UserError!]!
}

type UserError {
    code: String!
    message: String!
    field: String
}
~~~

For example, `OUT_OF_STOCK` can be a `userError` if the client needs to display the reason and allow adjusting the cart. Unexpected exceptions should still go through GraphQL error handling with safe messages, stable error codes, and internal logs.

Do not use payload errors to mask every failure. Distinguish user-correctable errors, valid but unsuccessful business states, and infrastructure errors that prevent the operation from completing.

## 20. Domain- and field-level authorization

Exposing a field in the schema does not mean every user is allowed to read it. Authorization needs to be checked in the service or resolver by principal, tenant, resource, and action.

~~~java
@SchemaMapping(typeName = "Order", field = "internalNotes")
public String internalNotes(Order order, Principal principal) {
    orderAccessService.checkCanReadInternalNotes(principal, order.id());
    return order.internalNotes();
}
~~~

This example illustrates checking policy before returning a field; actual implementation may use method security, an authorization service, or a reactive result depending on the stack.

Do not rely on clients simply not querying a field to protect data. Do not put internal fields into the schema if clients do not need them. For sensitive fields, use field-level authorization and test both direct access and access through nested resolvers.

If data is tenant-scoped, every repository query, downstream call, and DataLoader batch must apply the tenant scope. Do not accept a tenant ID from input if the server can determine it from the security context.

## 21. Organizing SDL by domain module

When a schema grows large, splitting SDL by capability or bounded context clarifies ownership:

~~~text
src/main/resources/graphql/
  common/
    scalars.graphqls
    pagination.graphqls
  catalog/
    product.graphqls
    product-search.graphqls
  ordering/
    order.graphqls
    place-order.graphqls
  customer/
    customer.graphqls
~~~

One file can declare a root type; other files extend it with `extend`:

~~~graphql
type Query {
    product(id: ID!): Product
}
~~~

~~~graphql
extend type Query {
    order(id: ID!): Order
    myOrders(first: Int = 20, after: String): OrderConnection!
}
~~~

Spring Boot can load multiple SDL resources according to schema location configuration. For example:

~~~properties
spring.graphql.schema.locations=classpath:graphql/**/
spring.graphql.schema.file-extensions=.graphqls,.gqls
~~~

Keep SDL files in the configured locations and verify that the schema merges successfully at application startup. Do not declare duplicate fields or conflicting type definitions across files.

## 22. Modularizing resolvers and application services

Organize packages by domain/capability instead of dumping all resolvers into one large class:

~~~text
com.example.shop/
  catalog/
    api/
      ProductQueryController.java
      ProductFieldController.java
      ProductSearchInput.java
    application/
      ProductQueryService.java
    domain/
      Product.java
      Money.java
    infrastructure/
      ProductRepository.java
  ordering/
    api/
      OrderQueryController.java
      OrderMutationController.java
      OrderFieldController.java
    application/
      PlaceOrderUseCase.java
      OrderQueryService.java
    domain/
      Order.java
      OrderLine.java
    infrastructure/
      OrderRepository.java
~~~

The package layout is just an example. What matters is that resolvers belong to the API layer, application services orchestrate use cases, the domain enforces invariants, and infrastructure implements persistence/clients.

Do not let SDL file structure become the sole domain boundary. Ownership must be reflected in code, module dependencies, and review processes.

## 23. Evolving the schema without breaking clients

A GraphQL schema is a contract that may be used by multiple clients simultaneously. Changes should favor additive evolution:

- Adding a new field is usually much lower risk than changing an existing field.
- Adding a required argument to an actively used field can break older clients.
- Changing a scalar or enum type can break code generation and client validation.
- Changing nullability from nullable to non-null is a breaking change.
- Removing an actively used field or enum value is breaking.
- Changing semantics while keeping the same name is also a behavioral breaking change.

When a field needs to be replaced:

1. Add the new field with clear semantics.
2. Keep the old field during the transition period.
3. Mark the old field with `@deprecated(reason: "...")`.
4. Monitor usage if instrumentation is available.
5. Notify clients and wait for adoption.
6. Remove only after confirming no consumers still rely on the old field.

Example:

~~~graphql
type Product {
    price: Float @deprecated(reason: "Use priceDetails for currency-aware pricing")
    priceDetails: Money!
}
~~~

This is a standalone migration example from an older schema with a `Float` `price`; it illustrates keeping the old field during the transition period while adding a new currency-aware field.

Do not add required arguments when extending a query; use an appropriate default or create a new field/use case. When adding enum values, keep in mind that some clients using exhaustive `switch` statements may not handle new values.

## 24. Avoiding over-fetching and under-fetching in design

GraphQL lets clients select fields, which can reduce response over-fetching. However, an overly generic schema or resolvers without a fetch plan can still cause the server to over-fetch data.

For example, if a client only needs `Product.name` but the resolver always loads all reviews, inventory history, and supplier details, the server still over-fetches.

Conversely, if clients must stitch together multiple separate queries for a single screen because the schema lacks appropriate composite fields, the API may under-serve the use case. Design queries and read models around real needs without turning the schema into a custom endpoint per UI pixel.

You can use projections, DataLoaders, `@BatchMapping`, selection set inspection, or dedicated query services to control loaded data. Only use selection set inspection for optimization when field-to-column mapping is clear and tested; avoid turning resolvers into hard-to-maintain custom query planners.

## 25. Testing domain-driven schemas

`GraphQlTester` can verify SDL, resolvers, nullability, and error contracts:

~~~java
@SpringBootTest
class ProductGraphQlTests {

    @Autowired
    GraphQlService graphQlService;

    private GraphQlTester graphQlTester;

    @BeforeEach
    void setUp() {
        graphQlTester =
            ExecutionGraphQlServiceTester.create(graphQlService);
    }

    @Test
    void exposesProductFieldsInDomainLanguage() {
        var response = graphQlTester.document("""
                query {
                    product(id: "p-100") {
                        id
                        name
                        price {
                            amount
                            currency
                        }
                    }
                }
                """)
            .execute();

        response.errors().verify();
        response.path("product.name")
            .entity(String.class)
            .isEqualTo("Mechanical Keyboard");
        response.path("product.price.currency")
            .entity(String.class)
            .isEqualTo("VND");
    }
}
~~~

Beyond response tests, verify:

- Fields and types are named in the ubiquitous language.
- Clients cannot write server-managed fields.
- Nullability aligns with domain invariants and partial failure behavior.
- Mutations invoke the right use cases and do not bypass aggregate rules.
- Authorization applies to both root and nested fields.
- Pagination maintains a stable sort order and enforces a page size cap.
- DataLoaders do not cause N+1 queries.
- Deprecated fields continue working during the transition period.
- Schema changes do not break client contracts.

You can add schema diffing or contract checks in CI to catch breaking changes before deployment.

## 26. Common design mistakes

| Mistake | Consequence | How to improve |
| --- | --- | --- |
| GraphQL type mirrors a JPA entity | API is coupled to persistence and leaks fields | Use GraphQL DTOs/read models |
| One Product type used across all bounded contexts | Mixes semantics and ownership | Separate snapshot/reference types when meanings differ |
| Generic `updateEntity` mutation | Bypasses domain commands and invariants | Model mutations as business actions |
| Input reuses output type | Clients can submit server-managed fields | Separate input and output types |
| Overly generic `status` field | Clients do not know which workflow the status belongs to | Use `orderStatus`, `paymentStatus`, `fulfillmentStatus` |
| Exposing all bidirectional relationships | Deep queries and hard-to-control graph | Only expose relationships backed by use cases |
| Unpaginated collections | Unbounded response sizes and queries | Connections, cursors, and page size caps |
| Non-null for fields with unstable dependencies | A minor failure nulls out the entire parent graph | Design nullability around invariants |
| Resolvers calling repositories directly in every field | Scattered business logic and transactions | Use application services/query services |
| Resolvers calling a service per parent | Network N+1 | Batch APIs and DataLoaders |
| Exposing internal fields and only hiding them in the UI | Data remains accessible through the API | Omit internal fields and enforce authorization |
| Changing semantics while keeping the field name | Clients receive unexpected data | Create a new field and deprecate the old one |
| Removing fields without checking consumers | Unexpected breaking change | Usage telemetry and schema contract checks |

## 27. Domain-driven schema design workflow

A practical workflow may include:

1. Identify bounded contexts and the owner of each concept.
2. Gather read use cases and commands from clients.
3. Choose types/fields using the ubiquitous language.
4. Distinguish the domain model, persistence model, and GraphQL read model.
5. Define aggregate boundaries, relationships, and snapshot semantics.
6. Separate inputs/outputs and define nullability, scalars, and enums.
7. Design pagination and error contracts for collections/use cases.
8. Determine field owners, authorization, and fetch strategies.
9. Map resolvers to application services with Spring GraphQL.
10. Test contracts, security, query counts, and schema evolution.
11. Review breaking changes before release.

## 28. Principles for domain-driven schema design

Start from the domain's language and use cases, not from database tables. Identify bounded contexts and the owner of each field; keep concepts with different semantics separate, even when they reference the same underlying record. Use GraphQL types to express the domain or read models that clients need, while JPA entities and domain aggregates continue serving their internal responsibilities.

Design Queries around read needs, Mutations around business actions, and keep Inputs/Outputs separate. Set nullability according to real invariants, paginate large collections, define clear error contracts, and protect fields by principal/tenant. In Spring for GraphQL, keep resolvers thin and delegate processing to application services; use `@SchemaMapping`, `DataLoader`, or `@BatchMapping` when resolving relationships.

Finally, treat the schema as a living contract: add fields in a backward-compatible way, deprecate before removing, and check for breaking changes in CI. A domain-driven schema helps clients understand the business accurately while allowing the system to evolve its databases, services, and implementations without forcing the API to change with every internal detail.

## References

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution.batch-loading)
- [GraphQL Specification — Type System](https://spec.graphql.org/)
- [Domain-Driven Design Reference](https://www.domainlanguage.com/ddd/reference/)
