# Distinguishing Storage ID, Resource URI, and Business Key

In a Spring Data REST application, a single record can be identified in several ways. For example, an order may have a database primary key of `42`, a business order code used by sales teams of `SO-2026-0042`, and be accessed via the URI `https://api.example.com/api/orders/42`.

These three values may relate to each other, yet they serve three distinct purposes:

- **Storage ID** identifies an entity in the persistence store, typically the database primary key.
- **Resource URI** identifies a resource in the HTTP contract used by clients.
- **Business key** identifies an object according to domain rules and carries meaning for users or business systems.

Clearly distinguishing these three concepts makes entity design, database relationships, APIs, and migrations more stable. In particular, do not assume that a database ID must always appear verbatim in URLs or that a business code must be used as the primary key.

## 1. A Running Example

Suppose an order management system has an entity:

| Concept | Example | Meaning |
|---|---|---|
| Storage ID | `42` | Primary key in the `orders` table |
| Business key | `SO-2026-0042` | Order number shown on invoices and in customer communications |
| Resource URI | `https://api.example.com/api/orders/42` | HTTP address for clients to read or operate on the order |

In the default Spring Data REST configuration, an item URI is typically constructed from the collection path plus the database identifier. Thus, if a repository is exported under `/orders` and the entity has ID 42, the default URI takes the form `/orders/42`.

However, the API can be configured to use a different identifier in the URI, such as the order number `SO-2026-0042`. In that case, the storage ID remains 42 and the business key remains SO-2026-0042; only how the resource is identified over HTTP changes.

## 2. Storage ID

The storage ID is the identifier used by the persistence layer to identify an entity. In JPA, the field annotated with `@Id` is the entity identifier. The database typically uses this value as the primary key and references it in foreign keys from related tables.

### 2.1. Characteristics

- Unique within the entity/table scope or the scope defined by the persistence store.
- Usually carries no business meaning.
- Can be auto-generated via identity, sequence, or UUID mechanisms.
- Used in relationships between records and persistence operations.
- Should remain stable throughout the entity's lifecycle.
- Usually has a simple type such as `Long`, `UUID`, or a composite key type.

JPA example:

~~~java
@Entity
@Table(name = "orders")
public class Order {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String status;

    protected Order() {
    }

    public Long getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
~~~

In this example, `id` is the entity's primary key. When saving a new entity, the database/provider generates the ID. The application does not need to ask the user to supply this ID.

### 2.2. Common ID Types

| Type | Example | Considerations |
|---|---|---|
| Numeric identity | `42` | Easy to use, compact, may reveal ordering or data volume |
| Numeric sequence | `10042` | Can be pre-allocated via sequence; still a technical ID |
| UUID | `8d3d...-...` | Can be generated distributedly with little reliance on a central generator; longer |
| Composite ID | `tenantId + localId` | More complex to represent and reference |
| Data store ID | MongoDB ObjectId, key of another store | Depends on the persistence store's mechanism |

An auto-incrementing numeric ID is not always the wrong choice. It is often convenient for primary keys and indexes. A UUID also does not automatically make a system more secure; authorization must still verify access permissions for each resource.

### 2.3. Storage ID Is Not a Security Token

Do not assume that an unpredictable ID prevents unauthorized access. If the API allows `GET /orders/42`, the server must still verify whether the caller has permission to view order 42.

Sequential IDs can make it easy for users to probe adjacent values. UUIDs can make URI guessing harder, but they do not replace authentication and authorization. A URI is not a secret token.

## 3. Business Key

A business key is a value used by the domain to identify an object according to real-world rules. It usually carries meaning for humans or integrated systems.

For example:

- Order number: `SO-2026-0042`.
- Product SKU: `SKU-AX19-BLK`.
- Book ISBN.
- Employee code issued by the company.
- Customer code in a CRM system.
- Transaction reference from a payment partner.

A business key can be a natural key if derived from naturally meaningful domain data. However, a seemingly natural value may still change, collide across scopes, or contain sensitive information.

### 3.1. Characteristics

- Meaningful in the domain and commonly used in business communication.
- Has its own generation rules, format, uniqueness scope, and lifecycle.
- May be a string, number, combination of multiple fields, or an external system code.
- May require a database unique constraint.
- May be immutable or mutable depending on business policy.
- Does not have to be the database primary key.

An order number may be unique across the entire system, or only unique within a given tenant/year/branch. Its uniqueness scope must be clearly defined. If a code is only unique within a tenant, constrain the pair `tenant_id, order_number`, not just `order_number`.

### 3.2. Adding a Unique Constraint for a Business Key

Example of an entity with a technical ID and a separate order number:

~~~java
import jakarta.persistence.*;

@Entity
@Table(
    name = "orders",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uk_orders_order_number",
            columnNames = "order_number"
        )
    }
)
public class Order {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(
        name = "order_number",
        nullable = false,
        updatable = false,
        length = 40
    )
    private String orderNumber;

    @Column(nullable = false)
    private String status;

    protected Order() {
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
~~~

Here:

- `@Id` defines the storage ID.
- `@GeneratedValue` lets the persistence provider/database generate the ID.
- `orderNumber` is the business key.
- `uniqueConstraints` instructs the database to guarantee order numbers do not collide.
- `updatable = false` indicates the order number cannot be updated through standard entity updates. Use this only if domain policy defines the code as immutable.

You can use `@Column(unique = true)` for a simple unique constraint. `@Table(uniqueConstraints = ...)` is useful when you need to name the constraint or create a multi-column unique constraint.

Checking uniqueness in Java before saving only provides early feedback. Two concurrent requests can still pass the check simultaneously. A database unique constraint is the final safeguard against storing duplicate values.

### 3.3. Mutable Business Keys

Not every business key is immutable. Email addresses, phone numbers, usernames, or customer codes may change through business workflows. If you use a mutable field as the long-term identifier for an entity, every URI or system referencing that field may be affected.

Before choosing a business key as a public ID, answer:

1. Is the value unique across the entire required scope?
2. Can the value change during the entity's lifecycle?
3. Can the value be reused after the entity is deleted?
4. Does the value contain personal information or internal data?
5. Do external systems depend on this value?
6. Must a tenant, issuer, or namespace be combined to prevent collisions?

If the answers regarding uniqueness or stability are unclear, keep the business key as a separate attribute with an appropriately scoped unique constraint.

## 4. Resource URI

A URI (Uniform Resource Identifier) identifies a resource within a namespace. A URL is a type of URI used to specify the location and access mechanism of a resource. In REST APIs, clients typically receive an HTTP URL as a resource's URI.

For example:

~~~text
https://api.example.com/api/orders/42
~~~ 

It can be broken down into:

| Component | Value | Role |
|---|---|---|
| Scheme | `https` | Protocol |
| Authority | `api.example.com` | Host and optional port |
| Base path | `/api` | API prefix |
| Collection path | `/orders` | Resource group |
| Item identifier | `42` | Item identifier in the URI |

A URI belongs to the API's HTTP contract. It lets clients identify and access resources exposed by the server. A URI does not have to be the database primary key, nor must it match the business key.

### 4.1. Default URIs in Spring Data REST

Suppose we have this repository:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository extends JpaRepository<Order, Long> {
}
~~~

With storage ID 42, Spring Data REST generates a default item URI like:

~~~text
/orders/42
~~~

If a base path is configured:

~~~properties
spring.data.rest.base-path=/api
~~~

The URI will look like:

~~~text
/api/orders/42
~~~

By default, Spring Data REST combines the collection path with the database identifier. Clients can obtain the URI from the `self` link in HAL responses or the `Location` header upon resource creation.

This is a default convention, not a strict rule that database IDs and resource URIs must match in every application.

### 4.2. The URI Is Part of the API Contract

Clients may store or bookmark URIs to access resources in subsequent calls. Therefore, changing the collection path, base path, item identifier, or host can impact clients.

Several principles:

- Use the `self` link returned by the server rather than manually assembling URIs from IDs.
- Avoid letting clients infer database structure from paths.
- Only change the URI strategy after evaluating the impact on clients and external integrations.
- Keep URIs stable within the committed API contract.
- Do not put sensitive data in URIs, as URIs commonly appear in logs, browser histories, proxies, and monitoring tools.

A resource URI can represent data aggregated from multiple tables, or an alternative representation of the same entity. Hence, a URI describes a resource at the API layer rather than a direct address of a database row.

## 5. How Do the Three Concepts Relate?

A common model is:

~~~mermaid
flowchart LR
    A[Business key<br/>SO-2026-0042] --> B[Domain entity<br/>Order]
    C[Storage ID<br/>42] --> B
    B --> D[Resource URI<br/>/api/orders/42]
    D --> E[HTTP client]
    E --> F[Spring Data REST]
    F --> B
~~~

The database uses the storage ID to manage entities and relationships. The domain uses the business key to apply business rules. The API uses the URI to expose resources to clients.

A request:

~~~http
GET /api/orders/42
Accept: application/hal+json
~~~

can be processed logically as follows:

1. Spring Data REST extracts the item identifier `42` from the URI.
2. The framework converts the identifier to the repository's ID type.
3. The repository looks up the entity with storage ID 42.
4. The returned entity has the business key `SO-2026-0042`.
5. The framework builds the representation and returns the resource's `self` link.

In the default configuration, the item URI contains the storage ID. If the application configures a custom entity lookup, steps 2 and 3 can use a different identifier.

## 6. Using a Business Key in Spring Data REST URIs

There are two distinct needs that are often confused:

- **Changing how the backend ID is represented:** for example, the technical ID is a UUID or composite ID, and you want to convert it into a suitable URI string.
- **Using another entity attribute as the resource identifier:** for example, wanting the URI to contain a username or order number instead of the database ID.

Spring Data REST provides separate mechanisms for these two needs.

### 6.1. Custom Entity Lookup

If you want item URIs to use a business key, Spring Data REST supports configuring an entity lookup. Example repository:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository extends JpaRepository<Order, Long> {

    Optional<Order> findByOrderNumber(String orderNumber);
}
~~~

Register the mapping from entity to business key and from business key back to entity:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;

@Configuration
public class SpringDataRestConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config) {

        config.withEntityLookup()
            .forRepository(OrderRepository.class)
            .withIdMapping(Order::getOrderNumber)
            .withLookup(OrderRepository::findByOrderNumber);
    }
}
~~~

With the configuration above:

- `Order::getOrderNumber` provides the identifier that appears in the item URI.
- `findByOrderNumber` locates the corresponding entity when the server receives a request.
- The entity's storage ID remains `Long id`.
- The business key must be unique within the repository lookup scope.

If an order has storage ID 42 and business key `SO-2026-0042`, the item URI can become:

~~~text
/orders/SO-2026-0042
~~~

Clients can GET the resource by business key:

~~~http
GET /orders/SO-2026-0042
Accept: application/hal+json
~~~

This is a significant change to the API contract. Before enabling it, verify whether the business key is stable, unique, non-sensitive, and safe for use in URIs. Also test generated links, update/delete operations, and associations pointing to the item resource.

If the business key is scoped per tenant, design the lookup so it cannot return an entity from the wrong tenant. Do not use a locally unique field as a global identifier if the URI does not include the necessary namespace.

### 6.2. BackendIdConverter

`BackendIdConverter` is an SPI that lets you customize how backend IDs are represented in URIs. It has two directions:

- `toRequestId(...)`: converts a backend ID into the string used in generated URIs.
- `fromRequestId(...)`: converts the string in a request into a backend ID so the repository can find the entity.

This mechanism is useful when you need to transform an ID representation, such as a composite ID or an opaque string. It does not by itself enforce domain business key rules. If you want to map from an attribute like order number to an entity, use an appropriate entity lookup.

Do not write a custom converter that encrypts IDs solely to obfuscate data and treat that as a security measure. Whether URIs use integers, UUIDs, or encoded strings, the server must still enforce access control.

## 7. Finding Entities by Business Key Without Changing the Item URI

It is not always necessary to put the business key into the item URI. You can keep URIs based on the storage ID and expose a query method for looking up by business key.

For example:

~~~java
@RepositoryRestResource(path = "orders")
public interface OrderRepository extends JpaRepository<Order, Long> {

    @RestResource(path = "by-order-number", rel = "by-order-number")
    Optional<Order> findByOrderNumber(
        @Param("orderNumber") String orderNumber
    );
}
~~~

Clients look up an order by business key:

~~~http
GET /orders/search/by-order-number?orderNumber=SO-2026-0042
Accept: application/hal+json
~~~

The response provides the order's representation and a `self` link to the item URI according to the current configuration, such as `/orders/42`.

This keeps the two roles clearly separated:

- The business key is a business search criterion.
- The item URI remains identified by the storage ID.

Use a query method when the business key might change or when you prefer not to make it a long-term resource identifier. If readable public URIs based on the business key are required, a custom entity lookup is a more deliberate choice.

## 8. Surrogate Key and Natural Key

Two common strategies when designing database keys:

### 8.1. Surrogate Key

A surrogate key is a technical ID without business meaning, such as `Long id` or a UUID.

Advantages:

- Rarely changes when business rules change.
- Easy to use as a foreign key.
- Independent of business key length or format.
- Can be pre-generated or distributed via an appropriate mechanism.

Disadvantages:

- Users cannot understand any meaning from the ID alone.
- Requires a separate business key field when the business needs a human-readable code.
- If sequential IDs are exposed, clients can guess other values; authorization is still required.

### 8.2. Natural Key

A natural key is a key taken from a domain-meaningful attribute, such as an ISBN or standardized product code.

Advantages:

- Can be used directly in business workflows and data exchange.
- Eliminates a separate code field if the value is truly stable and unique.
- Useful when system integrations require the same shared identifier.

Disadvantages:

- Can change due to policy or external issuer updates.
- May be long, complex, or contain sensitive information.
- May only be unique within a specific scope.
- If used as primary key, changes can ripple across many foreign keys and related systems.

For most business applications, a pragmatic design is to use a surrogate key as the primary key while keeping the business key in a separate column with an appropriate unique constraint. Use a natural key as the primary key only when the domain truly guarantees long-term stability, uniqueness, and scope.

## 9. Composite Business Keys and Uniqueness Scope

A business key can be composed of multiple fields. For example, an order number that is only unique within each tenant:

~~~java
@Entity
@Table(
    name = "orders",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_orders_tenant_number",
        columnNames = {"tenant_id", "order_number"}
    )
)
public class Order {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "order_number", nullable = false)
    private String orderNumber;
}
~~~

Here, `orderNumber` is not globally unique. The real business key is the pair:

~~~text
(tenantId, orderNumber)
~~~

If the API only uses `/orders/{orderNumber}`, the server cannot uniquely identify an entity when two tenants use the same code. You can choose one of these approaches:

- Include the tenant or namespace in the URI.
- Use a globally unique public identifier.
- Keep item URIs based on the storage ID and use tenant-checked query methods.
- Use a custom entity lookup explicitly scoped to the tenant from the security context.

Do not concatenate strings arbitrarily without clear escaping and parsing rules. If a composite ID must appear in a URI, consider a dedicated converter and test round-trip conversion thoroughly.

## 10. Risks of Using Business Keys in URIs

### 10.1. Business Key Changes

If an order number changes, old URIs may no longer find the entity. Clients storing old URIs will encounter errors or require redirects/aliases. If URIs have been shared with partners, migration is far more complex than updating a database column.

Only use a business key in URIs when policy defines it as stable. If it can still change, consider surrogate/public IDs for URIs and use the business key as a search parameter.

### 10.2. Business Keys Containing Personal Data

Email addresses, phone numbers, ID card numbers, or usernames can be business identifiers, yet they are not necessarily suitable for URLs. URIs are routinely written to access logs, reverse proxies, monitoring tools, and browser histories.

Use a dedicated public code if you need to identify resources without exposing personal information.

### 10.3. Collisions and Code Reuse

A uniqueness check in a service is not sufficient for concurrent requests. A database unique constraint and proper constraint-violation error handling are required.

You must also decide whether a business key can be reused after an entity is deleted. For instance, an employee code may need to be retained for auditing and never reassigned to someone else.

### 10.4. Confusing Keys with Authorization

Never assume that someone who knows a business key or URI is authorized to operate on the entity. Every request still needs permission checks based on user, tenant, business state, and target resource.

### 10.5. Impact on Integrations and Migrations

Changing a storage ID can affect foreign keys and internal references. Changing a URI can affect clients and external integrations. Changing a business key can affect domain rules, invoices, reports, and partner systems.

Manage these three types of changes as three separate contracts.

## 11. Choosing a Design for a Spring Data REST Application

Use the following questions to decide:

| Requirement | Usually Suitable Design |
|---|---|
| Need compact, stable primary keys for the database | Surrogate storage ID |
| Need readable codes for users and invoices | Separate business key with unique constraint |
| API should not expose database IDs | Public identifier or custom entity lookup |
| Business key can change | Keep item URIs based on a stable ID, use search endpoint |
| Business key is only unique within a tenant | Tenant-scoped unique constraint and lookup |
| Backend ID is composite or requires encoding | Consider `BackendIdConverter` |
| Clients need to discover actual URIs | Return HAL links and require clients to follow the `self` link |

A balanced default choice is often:

1. Use `Long id` or UUID as the storage ID.
2. Use `orderNumber` as the business key with a unique constraint.
3. Let Spring Data REST expose item URIs using the storage ID unless otherwise required.
4. Expose a query method to search by order number.
5. Switch item URIs to the business key only when it is truly immutable and intentionally part of the API contract.

## 12. Testing and Verification

Test each identification layer separately:

- **Storage ID:** save entities and verify the primary key is generated; foreign key relationships reference the correct entity.
- **Business key:** test valid keys, duplicate keys, malformed keys, key changes, and tenant scoping.
- **Resource URI:** GET via the `self` link, verify generated URIs are accurate; verify POST returns `Location`; verify clients still work when a base path is configured.
- **Custom entity lookup:** GET by business key, verify the exact entity is found and duplicate business keys cannot produce ambiguous results.
- **Security:** attempt to access a valid URI belonging to another tenant; the server must reject it according to policy.
- **Migration:** verify legacy URIs and legacy business keys when identifiers change.

Integration test example for a query method by business key:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderBusinessKeyTests {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void findsOrderByBusinessKey() throws Exception {
        mockMvc.perform(get(
                "/orders/search/by-order-number"
            )
            .param("orderNumber", "SO-2026-0042")
            .accept("application/hal+json"))
            .andExpect(status().isOk());
    }
}
~~~

This test assumes sample data has been prepared and the repository exports the corresponding query method. In a complete test, also assert the ID, business key, `self` link, and caller permissions.

## 13. Common Pitfalls

- **Using business keys as primary keys out of habit:** if values can change, relationships and migrations become painful.
- **Assuming URIs always contain database IDs:** that is Spring Data REST's common default, but entity lookup or ID converters can override it.
- **Assuming business keys are automatically unique:** scope must be defined and enforced by database constraints.
- **Putting secrets in URIs:** URLs get logged and cached in many intermediate systems.
- **Using UUIDs in place of authorization:** hard-to-guess IDs do not stop unauthorized access if the server omits permission checks.
- **Changing a business key without considering clients:** if the business key is in the URI, old links will break.
- **Treating query methods like custom item URIs:** searching by business key and identifying an item URI are two different API exposure patterns.
- **Failing to distinguish BackendIdConverter from EntityLookup:** one transforms backend ID representation; the other maps a resource identifier value to an entity.

## 14. Design Checklist

- [ ] The entity has a stable storage ID annotated with `@Id`.
- [ ] The business key is clearly defined in terms of format, uniqueness scope, and mutability.
- [ ] The database has unique constraints matching business key rules.
- [ ] Resource URIs are treated as an API contract, decoupling clients from the database schema.
- [ ] Clients use the `self` link from HAL responses.
- [ ] If custom entity lookup is used, bidirectional mapping works unambiguously.
- [ ] If BackendIdConverter is used, URI ID and backend ID conversion round-trips cleanly.
- [ ] Authorization is verified independently of whether IDs are predictable.
- [ ] Tests exist for duplicate keys, tenant scoping, legacy URIs, and business key changes.

## 15. References

- [Spring Data REST Reference — Customizing item resource URIs](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html): describes default item URI generation and custom entity lookup configuration.
- [Spring Data REST API — BackendIdConverter](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/webmvc/spi/BackendIdConverter.html): SPI for converting backend IDs to URI strings and back.
- [Spring Data REST Reference — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): describes collection and item resources, HTTP methods, and HAL links.

Storage ID, business key, and resource URI may all point to the same entity, yet they represent three distinct layers of responsibility. Good design keeps storage IDs stable, keeps business keys aligned with domain rules, and makes URIs clear, reliable HTTP identifiers for clients.