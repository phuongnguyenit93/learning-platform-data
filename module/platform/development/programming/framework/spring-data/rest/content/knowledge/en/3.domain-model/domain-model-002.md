# Choosing Domain Models Suitable for Direct REST Exposure

Spring Data REST can export Spring Data repositories as REST resources. Whatever domain type a repository manages becomes the basis for collection resources, item resources, and supported HTTP operations. Therefore, choosing a domain model for direct REST exposure is also choosing the data boundaries, relationships, and operations visible to external clients.

Not every entity in the database should have its own REST repository. Suitable models typically have clear business meaning, a stable identifier and lifecycle, an understandable consistency boundary, and data that can be exposed without leaking internal structure. For objects that only make sense inside a larger object, consider keeping them as components of an aggregate rather than turning each one into an independent resource.

## 1. How Does Spring Data REST Expose a Domain Model?

Spring Data REST takes repositories as its starting point. For example:

~~~java
public interface OrderRepository extends CrudRepository<Order, UUID> {
}
~~~

This repository can create a collection resource at a path derived from the domain type name, such as `/orders`, along with an item resource `/orders/{id}`. The name and path can be customized using `@RepositoryRestResource`.

The HTTP methods provided depend on the exported repository methods. With a CRUD-style repository, the collection typically supports GET and POST; items typically support GET, PUT, PATCH, and DELETE. Operations can be hidden by omitting them or using `@RestResource(exported = false)` on the appropriate method.

This means selecting a repository does not only decide which data can be read. It can also expose the ability to create, replace, update, or delete objects over HTTP. Treat the repository as part of the API contract.

Spring Data REST represents resources using HAL JSON by default. Responses include data alongside links so clients can discover collections, items, searches, and relationships. Clients can follow published links instead of manually constructing URLs from internal server conventions.

## 2. Start from Business Concepts and Lifecycles

A domain type suitable for direct exposure should represent a concept that API consumers understand. For example:

- `Order`: an order with a code, status, creation timestamp, and order lines.
- `Customer`: a customer with an identity and publishable profile information.
- `Product`: a product in the catalog.
- `Shipment`: a shipment with status and delivery history.

A type that exists only to support storage is usually not a good resource. For example, `OrderSequence`, `OrderAuditRow`, `InternalPricingCache`, or a purely technical join table may have no independent meaning to API consumers.

Ask the following questions when evaluating a domain type:

1. Can API users name and understand this object as a standalone resource?
2. Does the object have a stable identifier for direct access?
3. Does it have its own lifecycle, or is it only created/deleted alongside another object?
4. Is there a business rule requiring all changes to pass through a coordinating object?
5. Can its attributes be exposed without revealing internal data?
6. Do CRUD operations accurately reflect the actions the API should allow?

For example, `Order` has an identifier, status, and lifecycle from creation to completion. It is usually a meaningful resource. `OrderLine` may just be part of an order: users do not create an order line independently, but instead add lines to an order that is in an editable state. In that case, `OrderLine` should typically be managed through `Order`.

## 3. Use the Aggregate Root as the Starting Point

In Domain-Driven Design, an aggregate is a group of objects that must be kept consistent within the same change boundary. Each aggregate has an aggregate root. Changes belonging to the aggregate are coordinated through the root; repositories are usually defined for aggregate roots.

Example of an order:

~~~mermaid
flowchart TD
    O["Order<br/>Aggregate Root"] --> L1["OrderLine"]
    O --> L2["OrderLine"]
    O --> L3["OrderLine"]
    O -. "reference to other aggregate" .-> C["Customer"]
    O -. "reference to other aggregate" .-> P["Product"]
~~~

`Order` is the root because it controls the order status and order lines. `OrderLine` is a component added, modified, or removed through `Order`. `Customer` and `Product` can be separate aggregates with their own lifecycles.

A suitable repository organization might look like:

~~~java
public interface OrderRepository extends CrudRepository<Order, UUID> {
}

public interface CustomerRepository extends CrudRepository<Customer, UUID> {
}

public interface ProductRepository extends CrudRepository<Product, UUID> {
}
~~~

If `OrderLine` only belongs to `Order`, there is no need to create `OrderLineRepository` simply because it is stored in a separate table. Creating a separate repository could allow clients to read or modify order lines independently, bypassing rules that `Order` needs to enforce.

A repository for the aggregate root lets clients operate on a clear business boundary. However, creating a repository for the root alone is not enough to guarantee all invariants hold when REST requests write data. Design binding, validation, write methods, and access permissions so changes still obey aggregate rules.

## 4. Distinguishing Independent Entities, Child Entities, and Value Objects

These three kinds of objects typically have different exposure approaches:

| Object Type | Characteristics | Exposure Considerations |
|---|---|---|
| Aggregate root | Has independent identity and lifecycle; coordinates aggregate invariants | Usually a candidate for a REST repository |
| Child entity | Has identity within the aggregate scope but is managed via the root | Usually managed by the root; expose separately only if truly needed with an independent lifecycle |
| Value object | Defined by value, no separate identity; typically immutable | Usually embedded in the root's representation rather than given its own repository |

For example, `Money(amount, currency)` is a value object. An `Address` can be a value object if it only describes one customer's address and changes alongside the customer. However, if addresses can be managed, shared, or referenced independently in the business domain, it may need its own identity and resource.

Do not decide based on the number of database tables. A separate table does not automatically mean a separate REST resource. API boundaries should follow business meaning and lifecycle, not the physical schema structure.

## 5. Designing Relationships Between Resources

When an attribute references another domain type, how Spring Data REST represents it depends on whether the referenced type has its own repository.

Suppose `Order` has a `customer` attribute:

- If `Customer` has an exported repository, the `Order` resource usually represents the relationship via a link to an association resource. Clients can follow the link to access the relationship.
- If `Customer` does not have its own repository, `Customer`'s data may be included directly in `Order`'s representation.
- If you do not want to display that relationship, you can use a projection or configure the association to be hidden.

HAL example when `Customer` is exported:

~~~json
{
  "status": "CREATED",
  "_links": {
    "self": {
      "href": "/orders/8b2"
    },
    "customer": {
      "href": "/orders/8b2/customer"
    }
  }
}
~~~

The `customer` link indicates where to access the relationship. It is not necessarily the direct URI of the Customer resource; clients should follow the link returned by the server.

For relationships within the same aggregate, a nested representation may be more suitable:

~~~json
{
  "status": "CREATED",
  "lines": [
    {
      "productCode": "BOOK-01",
      "quantity": 2,
      "unitPrice": {
        "amount": 15.00,
        "currency": "USD"
      }
    }
  ]
}
~~~

The actual representation depends on mappings, exported repositories, projections, and serializers.

### 5.1. Avoid Creating Resources for Every Relationship

If a relationship only makes sense inside an aggregate, exposing it as a standalone endpoint can allow clients to mutate state in unintended ways. For example, if `OrderLine` can be edited separately via `/orderLines/{id}`, a client could change the quantity of an already confirmed order without going through `Order`'s rules.

Conversely, if `Customer` is a separate aggregate with an independent lifecycle and access controls, providing a Customer resource can make sense. `Order` can reference Customer via an association link rather than duplicating the entire customer profile in every response.

### 5.2. Be Careful with Bidirectional Relationships

Object graphs with bidirectional references can easily produce overly deep representations or serialization loops. For example, `Order` holds a list of `OrderLine`, while each `OrderLine` references back to `Order`.

Do not let internal Java structure randomly dictate the JSON shape. Explicitly decide which relationships are represented as links, which are embedded, and which are hidden. You can use projections, serialization annotations, or separate response models when strict control is required.

## 6. Choosing Which Attributes Are Allowed to Be Exposed

Spring Data REST renders a default view of an exported domain model. By default, many object properties are included in the representation, except the identifier according to the exporter's mapping rules. Therefore, an entity designed for persistence is not necessarily safe to expose as-is.

Do not directly expose the following data in API resources:

- Passwords, password hashes, reset tokens, or credentials.
- Secret keys, access tokens, and integration authentication details.
- Internal operational or calculation fields.
- Personal information that the current client is not authorized to view.
- Values that could reveal internal rules or another tenant's data.

For example, a `User` used for authentication might contain `passwordHash`, `rolesInternal`, and `resetToken`. If its repository is exported, those attributes must be excluded from the representation and corresponding write operations must be protected.

Do not rely on obscure field names or frontend UI to keep data secret. Authorization must be enforced on the server for collections, items, searches, and association resources alike.

## 7. Using Projections and Excerpts to Tailor Representations

When the domain model fits the resource but the client only needs a subset of data, Spring Data REST supports projections.

For example, the `Order` resource has many properties, but a list view only needs the ID, status, and total amount:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.data.rest.core.config.Projection;

@Projection(name = "orderSummary", types = Order.class)
public interface OrderSummary {

    UUID getId();

    OrderStatus getStatus();

    BigDecimal getTotal();
}
~~~

Clients can request a projection via the `projection` query parameter if the projection is registered and exported for the resource:

~~~http
GET /orders/8b2?projection=orderSummary
~~~

An excerpt projection can be declared on the repository:

~~~java
@RepositoryRestResource(
    path = "orders",
    excerptProjection = OrderSummary.class
)
public interface OrderRepository extends CrudRepository<Order, UUID> {
}
~~~

An excerpt is used as the default view when the resource appears in a collection or inside a related resource. An excerpt projection is not automatically applied to an item resource when a client GETs a single item directly; the client must request the corresponding projection explicitly.

Projections help tailor presented data. They do not change aggregate boundaries, do not replace authorization, and do not automatically turn an unsuitable domain model into a good API contract.

### 7.1. Projections Can Expose Data

Projections can add attributes that were otherwise hidden from the default JSON representation. Thus, a field marked `@JsonIgnore` can still appear if a projection is designed to read that field.

When creating a projection, treat every getter as a data exposure decision. Do not assume `@JsonIgnore` is an absolute security boundary if the API still supports projections. For sensitive data, check both registered projections and caller permissions.

## 8. Evaluating Write Capabilities and Protecting Invariants

Exposing a repository can surface POST, PUT, PATCH, or DELETE corresponding to repository methods. This works well when direct CRUD is a valid business operation.

Reconsider if:

- An order can only be created through a multi-step checkout workflow.
- Order status can only transition according to a state machine.
- Product prices must be fetched from the catalog and snapshotted at order placement time.
- Inventory quantities can only change through reservation or restocking workflows.
- A change requires checking multiple aggregates or calling external services.
- An operation must emit events, record audits, or execute ordered side effects.

In those cases, a direct CRUD endpoint may fail to express the real business action. Use a service/controller for the use case, such as `POST /orders/{id}/confirm`, `POST /orders/{id}/cancel`, or `POST /checkout`. The service enforces rules and transactions; the repository can remain internal.

If you only need to hide one repository method from the REST API, use `@RestResource(exported = false)` on the method. If you need to hide the entire repository, use `@RepositoryRestResource(exported = false)` or configure an appropriate detection strategy.

Hiding a method does not mean the entire business rule is protected. Another endpoint might still invoke the same repository, and access permissions must still be checked on the server.

## 9. Performance and Representation Size Considerations

A business-appropriate domain model can still produce a slow API if responses pull in too many relationships.

Consider:

- Whether collections support pagination.
- Whether each item triggers loading many associations.
- Which relationships need only links and which need embedded data.
- Which projections fit list views versus detail views.
- Whether N+1 queries occur when serializing collections.
- Whether clients genuinely need the entire graph in one response.

Spring Data REST can provide pagination and page navigation links when the repository supports `Pageable`. Do not assume large collections should be returned in full in a single response.

A common strategy is using a concise excerpt projection for collections; item resources provide full details; related aggregates are accessed via links. This allows clients to fetch only the data they need while keeping representations easy to navigate.

## 10. When Should You Not Expose Domain Models Directly?

Direct exposure works well when the domain model and the API resource share the same meaning, share the same boundaries, and can evolve relatively in sync. If the two models diverge, create a separate API layer.

| Scenario | Suitable Approach |
|---|---|
| Simple CRUD on an aggregate root with publishable data | Direct Spring Data REST |
| Domain model has many internal fields, but only some are needed for reading | Projections, excerpts, and representation configuration |
| API needs a JSON contract independent of entities and schema | Separate DTOs or representation models |
| A request executes a multi-step business workflow | Service and custom controller |
| Access permissions depend on tenant, status, or individual fields | Explicit authorization; often requires service/controller or dedicated protection |
| A resource aggregates data from multiple aggregates or systems | Query service and DTO/custom endpoint |
| API needs versioning independent of the persistence model | Separate API model and controller |

DTOs are not a sign of over-engineering. They are useful when the API has a different lifecycle, field naming, validation rules, or visibility scope from the domain model.

You can keep Spring Data Repositories for data access without exporting them. Services and controllers call the repository, map data to DTOs, enforce authorization, and execute use cases. That way, the persistence model can evolve without forcing clients to change alongside it.

## 11. Model Selection Example for a Sales System

Suppose a system has the following domain types:

~~~mermaid
flowchart TD
    O["Order"] --> L["OrderLine"]
    O --> C["Customer"]
    L --> P["Product"]
    O --> A["PaymentAttempt"]
    O --> H["OrderHistory"]
~~~

They can be evaluated as follows:

| Domain Type | Initial Decision | Reason |
|---|---|---|
| Order | Export repository | Has identity, lifecycle, and is an aggregate root |
| OrderLine | Keep inside Order | Line changes must obey Order status and rules |
| Customer | Can export separate repository | Has its own lifecycle and access controls; Order references Customer |
| Product | Can export read-only or via catalog API | Product belongs to catalog; price/inventory updates have separate workflows |
| PaymentAttempt | Usually do not export direct CRUD | Detail of payment workflow, requires side-effect control |
| OrderHistory | Usually read-only via query resource | History must preserve immutability and auditability |

These are business-dependent decisions, not rigid rules. If the system allows users to manage shipping addresses independently, `Address` can become its own resource. If the address is just a snapshot at order time, it should be part of Order data and not change automatically when the Customer profile is updated.

Example repository for an aggregate root:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository extends CrudRepository<Order, UUID> {
}
~~~

If the application does not want clients to delete orders directly, the delete method can be hidden from REST exposure and a dedicated business action provided instead:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository extends CrudRepository<Order, UUID> {

    @Override
    @RestResource(exported = false)
    void deleteById(UUID id);
}
~~~

An order cancellation API action can be implemented via a service/controller to check status, restock inventory, or coordinate payment according to system rules.

## 12. Decision Process Before Exporting

For each domain type considered for exposure, step through these decisions in order:

1. Identify the business concept and API consumers.
2. Identify identity, lifecycle, and aggregate root.
3. Classify relationships as external aggregates, child entities, or value objects.
4. Decide which repositories are permitted to be exported.
5. Choose which attributes and associations are visible.
6. Determine which HTTP methods accurately reflect valid business operations.
7. Evaluate authorization, tenant boundaries, and sensitive data.
8. Determine pagination, projections, and relationship loading depth.
9. Decide whether the domain model can serve as a long-term API contract or whether separate DTOs/controllers are needed.

Document the rationale for every repository exported or left unexported. This prevents an internal repository from accidentally becoming a public API simply because it was created for persistence.

## 13. Key Takeaways

- Spring Data REST exports repositories as collection and item resources; repository structure determines the exposed HTTP methods.
- Aggregate roots are usually a good starting point for choosing repositories and resource boundaries.
- Child entities should be managed through the root if their lifecycle and invariants depend on the aggregate.
- Value objects are usually embedded in representations rather than having their own repositories.
- Associations with separate repositories are usually represented as links; types without repositories may be embedded as inline data.
- Projections and excerpts customize representations, but do not replace authorization.
- Direct CRUD fits standard data operations; multi-step business workflows should go through services/controllers.
- Do not let database table structure dictate API structure.

## 14. Official Documentation

- Spring Data REST — Repository resources: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
- Spring Data REST — Projections and excerpts: https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html
- Spring Data Commons — Repository abstraction: https://docs.spring.io/spring-data/commons/reference/repositories.html
- Spring Data Relational — Domain-driven design and aggregates: https://docs.spring.io/spring-data/relational/reference/jdbc/domain-driven-design.html
