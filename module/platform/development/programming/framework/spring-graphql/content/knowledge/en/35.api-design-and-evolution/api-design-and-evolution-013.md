# Avoiding Overly Broad Schemas in GraphQL

GraphQL lets clients select many fields and traverse relationships in a single request. This flexibility easily leads to schemas with too many fields, types shared across every business workflow, inputs containing dozens of filters, and unbounded nested relationships. The result is an API that is hard to understand, hard to secure, hard to optimize, and hard to evolve without breaking clients.

Avoiding an overly broad schema does not mean capping the number of fields at a hard number. The goal is to keep the API surface sized appropriately for real use cases, reflect clear business boundaries, and serve data on demand in a controlled way. In Spring for GraphQL, design starts with SDL; controllers, services, DataLoaders, and security must uphold the schema's intent.

## Signs a schema is becoming too broad

A schema may already be too broad when several of these symptoms appear:

- An object type holds fields from multiple roles or bounded contexts, even though different clients only need different subsets of data.
- Root `Query` and `Mutation` have overly generic fields like `getEntity`, `search`, or `update` accepting type names or JSON to decide behavior at runtime.
- One input object merges filters from multiple screens or workflows, with most fields meaningful in only a few requests.
- Relationships return unpaginated lists, or allow clients to traverse deeply across many relationship layers without limits.
- Multiple duplicate-meaning fields exist with slight naming variations or serve only one legacy client that is no longer used.
- The public schema exposes internal fields, sensitive data, or actions callers should not access.
- Resolvers accumulate many branches by role, tenant, status, or field name because a single type carries too many responsibilities.
- Every business change forces edits to one giant type and risks breaking unrelated clients.

Counting fields alone is not enough to judge a schema overly broad. A type with many fields belonging to one stable concept can still be reasonable. Conversely, a small type that funnels unrelated behaviors into one generic mutation is also hard to maintain.

## Start from use cases and bounded contexts

Design a GraphQL schema from the questions clients need to answer, rather than copying entire database tables into types. A table may hold columns for operations, auditing, billing, and support; that does not mean every column belongs as a public field on a single GraphQL object.

For example, a bookstore system has distinct use cases:

| Use case | Data clients need |
| --- | --- |
| Catalog page | Title, cover image, display price, author, stock availability. |
| Book detail page | Description, publisher, genre, reviews, and publication info. |
| Order management | Order status, line items, total amount, and shipping history. |
| Warehouse operations | SKU, bin location, available quantity, and receiving info. |

There is no need to cram all of this data into a single `Book` type. You can create types representing distinct concepts and clear ownership, or separate fields with proper authorization. The choice depends on whether the fields share the same business meaning and lifecycle.

## Avoid an object type carrying every responsibility

Example of an overly broad design:

```graphql
type Customer {
  id: ID!
  name: String!
  email: String
  phone: String
  passwordHash: String
  roles: [String!]!
  internalNotes: String
  invoices: [Invoice!]!
  supportTickets: [SupportTicket!]!
  riskScore: Float
  creditLimit: Float
  warehouseAssignments: [Warehouse!]!
  auditEvents: [AuditEvent!]!
}
```

This type mixes profile data, authentication, billing, support, risk, warehouse, and audit concerns. It creates a contract that is hard to protect and can cause queries to load heavy relationships.

A design with clearer responsibilities:

```graphql
type CustomerSummary {
  id: ID!
  displayName: String!
}

type CustomerProfile {
  id: ID!
  displayName: String!
  contact: CustomerContact
}

type CustomerContact {
  email: String
  phone: String
}

type Invoice {
  id: ID!
  number: String!
  total: Money!
  status: InvoiceStatus!
}

type SupportTicket {
  id: ID!
  subject: String!
  status: TicketStatus!
}

type Query {
  customer(id: ID!): CustomerProfile
  myInvoices(first: Int = 20, after: String): InvoiceConnection!
  mySupportTickets(first: Int = 20, after: String): SupportTicketConnection!
}
```

The new types model each meaningful slice of the contract. `CustomerSummary` can serve lists; `CustomerProfile` serves profile views; invoices and support tickets are accessed via separate paginated queries.

You do not always need separate types solely because fields have different access permissions. GraphQL field authorization must still be enforced on the server; placing fields in dedicated types clarifies contracts and use cases, rather than replacing permission checks.

## Avoid overly generic root fields and broad CRUD

Root fields are the main entry points of the API. Field names should describe business resources or actions rather than forcing clients to pass class names, table names, or arbitrary commands.

Overly generic design:

```graphql
type Query {
  getEntity(type: String!, id: ID!): JSON
  search(type: String!, filter: JSON): [JSON!]!
}

type Mutation {
  saveEntity(type: String!, id: ID, payload: JSON!): JSON
  execute(command: String!, arguments: JSON): JSON
}
```

Clients do not know the contract for each data kind. The schema cannot validate fields, data types, or payload relationships; authorization and validation get pushed into runtime branches. Codegen cannot produce safe types either.

Use-case-driven design:

```graphql
type Query {
  book(id: ID!): Book
  searchBooks(input: BookSearchInput!): BookConnection!
  order(id: ID!): Order
  myOrders(first: Int = 20, after: String): OrderConnection!
}

type Mutation {
  createBook(input: CreateBookInput!): BookPayload!
  placeOrder(input: PlaceOrderInput!): PlaceOrderPayload!
  cancelOrder(input: CancelOrderInput!): CancelOrderPayload!
}
```

These fields can be backed by separate controllers and services. The schema expresses clear inputs and outputs, giving validation, authorization, documentation, and client code generation a solid foundation.

There is no need to create a separate mutation for every database column. Name mutations after meaningful business actions such as `placeOrder`, `cancelOrder`, and `changeShippingAddress`; each use case can update multiple tables inside an application service.

## Design specialized inputs per use case

A single `SearchInput` shared system-wide often grows into a giant object full of nullable fields, making it hard to tell which fields are valid in which context.

Example generic input to avoid:

```graphql
input SearchInput {
  text: String
  customerId: ID
  bookId: ID
  orderId: ID
  invoiceStatus: String
  ticketStatus: String
  warehouseId: ID
  minPrice: Float
  maxPrice: Float
  createdAfter: String
  createdBefore: String
  includeArchived: Boolean
  includeDeleted: Boolean
  sortBy: String
  sortDirection: String
  ...
}
```

Replace it with clearly scoped inputs:

```graphql
input BookSearchInput {
  keyword: String
  authorId: ID
  category: BookCategory
  minPrice: Money
  maxPrice: Money
  publishedAfter: Date
  publishedBefore: Date
  first: Int = 20
  after: String
}

input OrderSearchInput {
  status: OrderStatus
  placedAfter: DateTime
  placedBefore: DateTime
  first: Int = 20
  after: String
}
```

Dedicated inputs let GraphQL validate the right filter types and give services meaningful command/query objects. If two use cases genuinely share a stable group of fields, reuse a small input type; do not invent a generic abstraction merely to save a few lines of SDL.

### Constraining filters and sorting

Do not let clients pass SQL column names, Java property names, or free-form sort expressions. Use enums for options with finite value sets:

```graphql
enum BookSortField {
  TITLE
  PRICE
  PUBLISHED_AT
}

enum SortDirection {
  ASC
  DESC
}

input BookSortInput {
  field: BookSortField!
  direction: SortDirection! = ASC
}
```

The server maps enums to an allowlist of permitted sort fields. Never concatenate client values directly into SQL/JPQL. Also cap combined filters, date ranges, page sizes, and query cost.

## Paginate every potentially large relationship

Unpaginated list fields are one of the primary reasons schemas and queries become hard to control. Example:

```graphql
type Author {
  books: [Book!]!
}
```

Clients can request an author's entire catalog. As data grows, the resolver can load too many records and produce abnormally large responses.

Add pagination to the field:

```graphql
type Author {
  books(first: Int = 20, after: String): BookConnection!
}

type BookConnection {
  edges: [BookEdge!]!
  pageInfo: PageInfo!
}

type BookEdge {
  cursor: String!
  node: Book!
}

type PageInfo {
  hasNextPage: Boolean!
  endCursor: String
}
```

Enforce `first` bounds on the server, such as 1 to 100. Default values keep older clients from having to pass the new argument; validation/services must still reject values outside bounds. Cursors should remain stable with the sort order and can use opaque encoding so clients do not depend on internal structure.

Potentially large relationships like orders, invoices, reviews, audit events, and support tickets should have pagination or dedicated queries. Not every list needs a connection: small enum lists or fixed-size value sets can be returned directly.

In Spring for GraphQL, bind the use-case-specific input into a dedicated record and check bounds before calling the service:

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

public record BookSearchInput(
        String keyword,
        String authorId,
        Integer first,
        String after) {
}

@Controller
public class CatalogQueryController {

    private final CatalogService catalogService;

    public CatalogQueryController(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @QueryMapping
    public BookConnection searchBooks(@Argument("input") BookSearchInput input) {
        int first = input.first() == null ? 20 : input.first();
        if (first < 1 || first > 100) {
            throw new IllegalArgumentException("first must be between 1 and 100");
        }
        return catalogService.search(input.keyword(), input.authorId(), first, input.after());
    }
}
```

This example assumes the schema has `searchBooks(input: BookSearchInput!): BookConnection!` and `BookSearchInput.first` is nullable with default `20`. In production applications, use an exception handler to map limit errors to a stable GraphQL client error code; never return stack traces or internal messages.

## Controlling query depth and complexity

GraphQL lets clients compose nested fields. A single query can multiply resolver executions exponentially if objects expose multiple list relationships.

Example of a dangerous unbounded query:

```graphql
query DeepCatalog {
  authors(first: 100) {
    books(first: 100) {
      reviews(first: 100) {
        comments(first: 100) {
          author {
            books(first: 100) {
              id
            }
          }
        }
      }
    }
  }
}
```

To protect the server, layer multiple defenses:

- Cap page sizes on every list field.
- Limit query depth to prevent overly deep nesting trees.
- Compute query complexity/cost per field, especially for lists and expensive resolvers.
- Set timeouts for downstream calls and database queries.
- Apply rate limits, authentication, and quotas per client/tenant.
- Use `DataLoader` or `@BatchMapping` to prevent N+1 when resolving relationships.
- Monitor latency, errors, and `DataFetcher`/SQL counts to calibrate the cost model.

A depth limit alone is insufficient: a shallow query can still request a list of hundreds of thousands of elements. A page size limit alone is also insufficient if clients nest multiple lists. Cost analysis should factor in both maximum element counts and field weights.

Spring for GraphQL runs on GraphQL Java and lets you integrate instrumentation through `GraphQlSource`. You can register query depth/complexity instrumentation matching your GraphQL Java version via Spring Boot's `GraphQlSourceBuilderCustomizer` or directly on the builder. Exact instrumentation APIs depend on the GraphQL Java version managed by your dependencies; do not copy a constructor from a different version without checking the dependency tree.

Business limits such as `first <= 100` must still be enforced in argument validation/services even when query complexity instrumentation is active.

## Do not expose a field just because the entity/database has it

The GraphQL schema is a public contract. The fact that a field exists on a JPA entity or database table does not mean clients should be allowed to read it.

Example of fields not to expose:

```graphql
type Employee {
  id: ID!
  name: String!
  salary: Money
  disciplinaryNotes: String
  managerPrivateComments: String
  accessToken: String
}
```

Sensitive fields such as access tokens, password hashes, private notes, or personal data should not become public GraphQL fields. For legitimate data restricted to certain roles, use field authorization and enforce permissions in services/resolvers. Omitting a field from the schema and enforcing access control are two separate decisions.

Example of a permission-protected field:

```java
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Controller;

@Controller
public class EmployeePrivateDataController {

    private final EmployeeService employeeService;

    public EmployeePrivateDataController(EmployeeService employeeService) {
        this.employeeService = employeeService;
    }

    @SchemaMapping(typeName = "Employee", field = "salary")
    @PreAuthorize("hasAuthority('employee:salary:read')")
    public Money salary(Employee employee) {
        return employeeService.salaryFor(employee.id());
    }
}
```

For method security to take effect, the application must enable method security and configure Spring Security appropriately. Having `@PreAuthorize` does not replace tenant or ownership checks in the service.

Never rely on disabling introspection as the primary way to hide sensitive fields. Clients can learn the schema from codegen, logs, or documentation; the server must still enforce authorization on every request.

## Splitting the schema into domain files in Spring for GraphQL

Large schemas can be split into multiple SDL files to simplify ownership and code review. This is source organization; it does not shrink the API surface on its own.

Example layout:

```text
src/main/resources/graphql/
├── catalog.graphqls
├── orders.graphqls
└── customers.graphqls
```

`catalog.graphqls` declares the root types:

```graphql
type Query {
  book(id: ID!): Book
  searchBooks(input: BookSearchInput!): BookConnection!
}

type Book {
  id: ID!
  title: String!
  author: Author
}
```

`orders.graphqls` extends `Query` and declares order types:

```graphql
extend type Query {
  order(id: ID!): Order
  myOrders(first: Int = 20, after: String): OrderConnection!
}

type Order {
  id: ID!
  status: OrderStatus!
  total: Money!
}
```

`customers.graphqls` can declare `extend type Query` for customer profiles and related types.

Spring Boot loads schema resources under `classpath:graphql/**/` by default. If you change the schema location, configure `spring.graphql.schema.locations` accordingly. In non-Boot applications, pass all schema resources to the `GraphQlSource` builder.

Declare the base `type Query` and `type Mutation` only once; other files use `extend type Query` or `extend type Mutation`. Splitting files by domain aids review and ownership, while gateways and clients still see one merged schema.

## When do you need multiple GraphQL services or Federation?

Do not split out a subgraph simply because an SDL file grew long. You can split files, controller packages, and service modules by domain inside the same application while keeping a single GraphQL endpoint.

Federation fits when domains are independently owned and deployed, have clear data boundaries, and need composition into a supergraph. Splitting subgraphs solely to reduce field count in a schema increases operational complexity: network calls, entity resolution, inter-service authentication, distributed tracing, and cross-service error handling.

Before splitting, determine:

- Which domain genuinely owns the entity and data?
- Which team owns the schema, resolvers, and operations?
- Is there a need for independent deployment or separate scaling?
- Are cross-subgraph call latencies and failure modes acceptable?
- Are entity keys, authorization, and data ownership clear?

If those needs do not yet exist, a modular monolith with domain-organized schema resources and application services is usually simpler.

## Keeping the schema lean over the API lifecycle

Broad schemas usually accumulate gradually through fields that get added and never revisited. Manage the field lifecycle actively:

1. Add fields for concrete use cases with specific clients and owners.
2. Document semantics, nullability, pagination, authorization, and error behavior.
3. Track usage before deprecating or removing fields.
4. Use `@deprecated(reason: "...")` to guide clients toward replacement fields.
5. Remove fields only after checking operation usage and migration timelines.
6. Keep schema diffs and operation checks in CI.

Example of deprecating a legacy field:

```graphql
type Query {
  customer(id: ID!): Customer
    @deprecated(reason: "Use customerProfile(id:) to fetch customer profiles.")
  customerProfile(id: ID!): CustomerProfile
}
```

The reason must point clients to a replacement field or flow that actually exists. Do not deprecate just to rename if no migration plan exists; both fields can coexist during the transition window.

## Testing the schema surface

Tests should do more than verify resolvers return expected data. Check the schema contract to prevent internal or overly generic fields from slipping in.

You can use `GraphQlTester` to run introspection in internal tests:

```java
@Test
void customerSchemaDoesNotExposePrivateCredentials() {
    graphQlTester.document("""
            query {
              __type(name: "CustomerProfile") {
                fields {
                  name
                }
              }
            }
            """)
            .execute()
            .path("__type.fields[*].name")
            .entityList(String.class)
            .doesNotContain("passwordHash", "accessToken", "internalNotes");
}
```

Introspection may be restricted in production; tests can inspect the built SDL or schema registry artifact rather than calling a public endpoint. The goal is confirming the public contract exposes only intended fields.

Query complexity/page size tests should send operations exceeding limits and confirm requests are rejected before resolvers burn resources. Authorization tests should call sensitive fields with both authorized and unauthorized principals. DataLoader tests should assert batch call counts or SQL query counts, not just correct responses.

## Roadmap for refactoring an overly broad schema

You do not need to redesign the entire schema at once. Reduce risk step by step:

1. **Inventory:** export current SDL, group root fields/types/inputs by domain, and identify fields lacking an owner.
2. **Observe usage:** see which operations actually call which fields, which clients use them, and at what frequency.
3. **Classify:** sensitive fields, duplicate-meaning fields, generic fields, unpaginated relationships, overly broad filters, and unused fields.
4. **Define target contracts:** add use-case-specific types/inputs/queries; establish pagination and authorization.
5. **Run in parallel:** add new fields, keep old fields, and route resolvers to appropriate application services.
6. **Migrate clients:** update operations, codegen, and contract tests.
7. **Deprecate and remove:** delete old fields only when usage shows no clients remain dependent.
8. **Monitor:** check latency, error rates, query complexity, DataLoader batching, and SQL counts after refactoring.

Do not change names or nullability at the same time as splitting domains unless necessary. Breaking changes into small steps keeps schema diffs and production issues easy to trace.

## Common design mistakes

| Practice | Problem | How to address |
| --- | --- | --- |
| Copying entire JPA entities into GraphQL types | Leaks internal fields and couples API to persistence | Design output types around contracts/use cases |
| One `SearchInput` across all domains | Many meaningless fields per request and complex validation | Use specialized inputs; reuse only genuinely stable field groups |
| `JSON` for every payload | Loses schema validation, codegen, and discoverability | Declare explicit input/output types; use JSON scalar only for truly opaque data |
| Generic `updateEntity` mutation | Fails to express business actions and invariants | Use use-case mutations like `cancelOrder` or `changeAddress` |
| Unpaginated relationship lists | Can load entire tables and produce huge responses | Use connections/cursors or dedicated queries |
| Depth limit alone | Shallow queries can still load massive lists | Combine page sizes, query cost, timeouts, and rate limits |
| Relying on separate types as authorization | Clients can still call fields if the server skips permission checks | Enforce permissions in resolvers/services and tenant scope |
| Splitting SDL files and assuming the schema shrunk | Only changes source layout; public contract stays identical | Evaluate API surface and domain boundaries separately |
| Splitting into Federation solely due to schema length | Adds unnecessary network, ownership, and ops overhead | Split only when independent bounded contexts/teams/deployments warrant it |
| Removing old fields right after adding new ones | Breaks existing clients | Track usage, deprecate, and migrate in phases |

## Key takeaways

Avoid overly broad schemas by designing from use cases and bounded contexts rather than mirroring the entire database model onto the API. Use specialized types and inputs, business-named root fields, paginated lists, constrained filters/sorts, and explicit field authorization. Bound query depth and complexity to protect runtime stability.

Splitting SDL across multiple files organizes source code without shrinking the public schema. Use Federation only when domain boundaries and independent deployment needs justify it. For existing schemas, observe usage, introduce new contracts in parallel, deprecate deliberately, and remove legacy fields only after clients migrate.

## References

- [GraphQL.org — Schema and Types](https://graphql.org/learn/schema/)
- [GraphQL.org — Best Practices](https://graphql.org/learn/best-practices/)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Boot — GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Apollo GraphOS — Schema Checks](https://www.apollographql.com/docs/graphos/platform/schema-management/checks)
- [Apollo GraphOS — Schema Design](https://www.apollographql.com/docs/graphos/schema-design/)
