# Distinguishing Entities, Value Objects, DTOs, and Aggregate Query Results

In a Spring Data Relational R2DBC application, data can appear in several forms: objects stored in the database, components forming a business model, data sent across an API, or results computed across multiple rows. These forms can share similar fields yet carry different semantics and lifecycles.

For example, customer information might be represented as:

- An **entity** with a stable identifier, such as a customer with ID 42.
- A **value object** such as an address, defined by its content.
- A **DTO** containing a name and address to return to a screen or API.
- An **aggregate query result** reporting how many customers exist in each status.

Distinguishing these categories properly clarifies domain models, schemas, repositories, and queries. In Spring Data Relational specifically, you must distinguish an entity from a Domain-Driven Design (DDD) aggregate root, and avoid confusing a DDD aggregate with the result of a SQL query using aggregate functions.

## 1. Entities

**An entity is an object with its own identity that persists across state changes.** Two objects with the same name and address can still be two distinct entities if they have different IDs. Conversely, an entity remains the same entity when its name, email, or address is updated.

Example:

| ID | Name | Email |
|---:|---|---|
| 42 | An | an@example.com |
| 57 | An | an@example.com |

The two rows above describe two separate customers even though their attributes currently match. The ID lets the system identify each customer individually.

In Spring Data Relational, an entity is mapped to a table using mapping annotations. Example:

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String name;

    private String email;

    private String status;

    protected Customer() {
    }

    public Customer(String name, String email, String status) {
        this.name = name;
        this.email = email;
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }

    public String getStatus() {
        return status;
    }
}
~~~

- **@Table** specifies the mapped table.
- **@Id** marks the identifier property.
- Spring Data uses mapping metadata to convert between data rows and Java objects.
- Repositories typically operate on entities or aggregate roots by ID.

Reactive repository example:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByStatus(String status);
}
~~~

An entity does not have to be an annotated class. Entity is a domain-modeling concept; Spring Data annotations help map that model to relational data.

### Entities in Spring Data Relational Are Not JPA-Managed Entities

This is a frequent point of confusion when moving from Spring Data JPA to Spring Data JDBC or R2DBC. Spring Data Relational can map a class with an ID as an entity, but it does not provide a JPA/Hibernate-style persistence context that tracks all managed objects and performs automatic dirty checking.

In the typical workflow:

- The application loads an aggregate through a repository.
- The application modifies object state.
- The application calls an appropriate save operation to persist changes to the database.
- Spring Data executes SQL statements according to its mappings and module rules.

Do not assume that mutating a property on a loaded object will cause Spring Data R2DBC to automatically detect and flush changes like Hibernate does inside a persistence context.

## 2. Aggregate Roots and Aggregate Boundaries

In DDD, an **aggregate** is a group of domain objects treated as a consistent unit. The **aggregate root** is the entity standing at the outer boundary of that group; external code accesses and requests changes to aggregate members through the root.

For example, an order might consist of:

- **PurchaseOrder:** the aggregate root, carrying an ID and order status.
- **OrderLine:** an order line belonging to the order.
- **Money:** a value object representing a monetary amount and currency.

A repository is typically designed around the aggregate root:

~~~java
public interface PurchaseOrderRepository
        extends ReactiveCrudRepository<PurchaseOrder, Long> {
}
~~~

Business code loads the order, invokes behavior on the root, and saves the aggregate per the model's rules. Order lines are managed as internal members of the aggregate rather than letting services arbitrarily update individual lines while bypassing order rules.

Spring Data Relational supports mapping aggregates and their members via mapping metadata. For example, **@MappedCollection** can map collections belonging to the root into a related table. Other aggregates are typically referenced by ID rather than embedding full object graphs inside the same aggregate.

Key distinction: an entity is an object with identity; an aggregate is a consistency boundary for a group of objects. Every aggregate root is an entity, but not every entity is necessarily an aggregate root.

## 3. Value Objects

**A value object is defined by the values of its attributes and has no independent identity.** If two value objects have the same values according to domain rules, they are considered equivalent even if constructed as two separate instances.

Address example:

~~~java
public record Address(
    String street,
    String city,
    String postalCode
) {
}
~~~

Two addresses with the same street, city, and postal code represent the same value. When a customer changes addresses, the domain typically replaces the old value object with a new value object; it does not necessarily update an independent Address entity.

Value objects typically exhibit these traits:

- No separate business ID.
- Equality based on attribute values.
- Should be immutable after creation to prevent unintended side effects.
- Can contain business rules and validate themselves.
- Usually live inside an entity or aggregate.

Money example:

~~~java
public record Money(
    BigDecimal amount,
    Currency currency
) {
    public Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);

        if (amount.signum() < 0) {
            throw new IllegalArgumentException(
                "Amount must not be negative"
            );
        }
    }
}
~~~

Money is not just two data columns. It can encapsulate rules such as forbidding negative amounts in a given context, checking currency compatibility when adding, and applying rounding rules.

### Mapping Value Objects in Spring Data Relational

A simple value object can be mapped into the same table as an entity using embedded mapping:

~~~java
public record Address(
    String street,
    String city,
    String postalCode
) {
}

@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String name;

    @Embedded(prefix = "address_")
    private Address address;
}
~~~

Properties of Address are mapped to columns on the customer table, such as:

| Column | Value |
|---|---|
| id | 42 |
| name | An |
| address_street | 12 Nguyen Trai |
| address_city | Ho Chi Minh City |
| address_postal_code | 700000 |

Prefixes help avoid column name collisions and clarify which columns belong to which value object. Capabilities and rules for handling embedded objects, including when all values are null, depend on the annotation and the Spring Data Relational version in use.

A value object can also be stored in a separate table as an aggregate member depending on the model and mapping. Residing in a separate table does not automatically turn it into an independent entity. Evaluate identity and lifecycle rules in the domain, not just table count.

## 4. DTOs (Data Transfer Objects)

**A DTO is an object used to transfer data across a boundary**, such as between a controller and service, between a service and an external client, or between a query layer and a UI screen. A DTO shapes the data to be transmitted without having to mirror the domain model or table structure.

For example, an API only needs to return a customer's ID, name, and city:

~~~java
public record CustomerResponse(
    Long id,
    String name,
    String city
) {
}
~~~

The Customer entity may hold email, status, full address, and internal attributes. The CustomerResponse DTO includes only the fields the API intends to expose.

Using DTOs offers several advantages:

- Prevents the database schema from directly dictating the API structure.
- Avoids accidentally exposing internal fields or sensitive data.
- Allows one API to combine data from multiple entities or sources.
- Enables field naming in API terminology rather than column names.
- Allows changing response shapes without modifying domain entities.

DTOs generally lack independent identity or persistence lifecycles. Two DTOs with identical contents can be viewed as equivalent data messages; that does not create two different customers.

### Input DTOs and Output DTOs

You do not need to share one DTO for both requests and responses.

Create-customer request example:

~~~java
public record CreateCustomerRequest(
    String name,
    String email,
    String street,
    String city,
    String postalCode
) {
}
~~~

The service validates data, builds the value object and entity:

~~~java
public Mono<CustomerResponse> create(
        CreateCustomerRequest request) {

    Address address = new Address(
        request.street(),
        request.city(),
        request.postalCode()
    );

    Customer customer = new Customer(
        request.name(),
        request.email(),
        address
    );

    return customerRepository.save(customer)
        .map(saved -> new CustomerResponse(
            saved.getId(),
            saved.getName(),
            saved.getAddress().city()
        ));
}
~~~

This example demonstrates the conversion boundary: a request DTO enters, domain objects are constructed and validated, the repository persists the entity, and a response DTO is built for external output.

Do not let controllers accept entities directly and bind every request field onto persistence objects. That can allow clients to alter properties the business does not intend to expose, such as IDs, approval statuses, or administrative flags.

## 5. Projections and DTOs Used for Queries

On the read side, applications often do not need to load full entities. A screen might only need a customer's name and order count. A **Projection** represents the subset of data to be read; a DTO is one form of class/record usable as a projection type.

Read model example:

~~~java
public record CustomerOrderCount(
    Long customerId,
    String customerName,
    Long orderCount
) {
}
~~~

This result is not a Customer entity. It is data produced from a join and count. Do not try to save it via CustomerRepository as if it were a full customer.

In Spring Data, projections can be expressed via interfaces or DTOs depending on query style and module capabilities. For custom SQL queries in R2DBC, DatabaseClient enables explicit column-by-column mapping into a DTO:

~~~java
Flux<CustomerOrderCount> results =
    databaseClient.sql(
        "SELECT c.id AS customer_id, " +
        "c.name AS customer_name, " +
        "COUNT(o.id) AS order_count " +
        "FROM customer c " +
        "LEFT JOIN purchase_order o ON o.customer_id = c.id " +
        "GROUP BY c.id, c.name"
    )
    .map((row, metadata) -> new CustomerOrderCount(
        row.get("customer_id", Long.class),
        row.get("customer_name", String.class),
        row.get("order_count", Long.class)
    ))
    .all();
~~~

Explicit mapping makes clear:

1. Which columns the SQL selects.
2. Which aliases are used for results.
3. Which Java types are requested when reading each column.
4. Which DTO is instantiated from each result row.

Appropriate Java types for aggregated columns can depend on the database and R2DBC driver. For example, COUNT typically maps to a wide integer type, though you should confirm with your actual driver and integration tests.

## 6. SQL Aggregate Query Results

In SQL, the term aggregate usually refers to summary calculations over a group of rows. Common functions include:

| Function | Meaning | Example |
|---|---|---|
| COUNT | Counts rows or non-null values | Number of customers |
| SUM | Computes sum | Total revenue |
| AVG | Computes average | Average order value |
| MIN | Finds minimum value | Earliest creation date |
| MAX | Finds maximum value | Latest creation date |

Example counting customers by status:

~~~sql
SELECT status, COUNT(*) AS customer_count
FROM customer
GROUP BY status;
~~~

Results might look like:

| status | customer_count |
|---|---:|
| ACTIVE | 120 |
| BLOCKED | 8 |
| PENDING | 15 |

Each row in the result represents a status group. It is not a Customer entity because no single customer corresponds to that row. Nor does it have to be stored in a table.

We can define a DTO for the result:

~~~java
public record CustomerStatusCount(
    String status,
    Long customerCount
) {
}
~~~

And map the result with DatabaseClient:

~~~java
Flux<CustomerStatusCount> counts =
    databaseClient.sql(
        "SELECT status, COUNT(*) AS customer_count " +
        "FROM customer GROUP BY status"
    )
    .map((row, metadata) -> new CustomerStatusCount(
        row.get("status", String.class),
        row.get("customer_count", Long.class)
    ))
    .all();
~~~

If the query returns only a single scalar value, Mono can be used:

~~~java
Mono<Long> totalCustomers =
    databaseClient.sql("SELECT COUNT(*) AS total FROM customer")
        .map((row, metadata) -> row.get("total", Long.class))
        .one();
~~~

Aggregate query results fit reports, dashboards, statistics, and read screens well. Because the calculation happens in the database, the application avoids loading all entities into memory to count them manually.

### Considerations When Using Aggregate Functions

- COUNT(*) counts rows; COUNT(column) skips rows where that column is null.
- SUM and AVG typically ignore null values; return types depend on column types and database engine.
- GROUP BY produces one result row per group defined by the grouping expressions.
- HAVING filters groups after aggregation; WHERE filters rows before grouping.
- One-to-many joins can multiply rows before COUNT or SUM is evaluated. Choose columns and query structure carefully to avoid double-counting.
- When a query might return zero rows, use an optional return type or Mono matching the query's semantics.

Example distinguishing WHERE and HAVING:

~~~sql
SELECT status, COUNT(*) AS customer_count
FROM customer
WHERE created_at >= :from_date
GROUP BY status
HAVING COUNT(*) >= 10;
~~~

WHERE limits which customers enter the aggregation. HAVING keeps only groups with at least 10 customers.

## 7. Do Not Confuse SQL Aggregate Results with DDD Aggregates

Both concepts share the word aggregate, yet mean completely different things:

| Concept | Meaning | Example |
|---|---|---|
| DDD aggregate | Group of domain objects with a consistency boundary and an aggregate root | Order together with its order lines |
| SQL aggregate | Computation over multiple rows of data | COUNT of orders by status |
| Aggregate query result | Values returned after calculations or GROUP BY | Status and order count |

A DDD aggregate is a way to organize the business model and control changes. A SQL aggregate is a computation inside a query. An aggregate root may be persisted across multiple tables; an aggregate query result may be computed from one or more tables without creating a new domain entity.

For example, PurchaseOrder is an aggregate root. A monthly revenue query may read many PurchaseOrder and OrderLine rows and return MonthlyRevenue. MonthlyRevenue is a reporting read model/DTO, not an aggregate root simply because the word aggregate appears in the query type.

## 8. Comparing the Four Data Categories

| Criterion | Entity | Value Object | DTO | Aggregate Query Result |
|---|---|---|---|---|
| Own identity | Yes | No | Usually no | Not necessarily |
| Comparison | By identity | By value | By data transfer purpose | By computed values |
| Domain lifecycle | Yes | Dependent on containing entity/aggregate | Scoped to data transfer | Scoped to query execution |
| Persisted in DB? | Usually yes | Stored with entity or as aggregate member | Not required | Usually computed at query time |
| Primary purpose | Represents an object with identity | Describes a business value | Transfers data across boundaries | Statistics, reports, analytics |
| Example | Customer | Address, Money | CustomerResponse | CustomerStatusCount |

Do not classify solely by class name or property count. A class with three fields could be a DTO, value object, or projection depending on its role and semantics.

## 9. Organizing Data Models in an R2DBC Application

A common structure keeps the domain model in the business layer, uses Spring Data Relational to map aggregates requiring persistence, and uses dedicated DTOs/projections at read/write boundaries.

Example structure:

~~~text
API
 |
 +-- CreateCustomerRequest
 |
 v
Application Service
 |
 +-- Validate input data
 +-- Create Address (Value Object)
 +-- Create Customer (Entity / Aggregate Root)
 |
 v
CustomerRepository
 |
 v
Spring Data R2DBC
 |
 v
Database

DatabaseClient / Query Repository
 |
 +-- SQL JOIN / GROUP BY / COUNT
 |
 v
CustomerStatusCount (DTO / Read Model)
 |
 v
API or Dashboard
~~~

Some design principles:

1. Use entities for objects requiring identity and a business lifecycle.
2. Use value objects for concepts defined by value that can encapsulate validation rules.
3. Keep aggregates small enough that consistency boundaries and save operations remain manageable.
4. Use separate DTOs for requests/responses so the entire persistence model is not exposed.
5. Use projections or DTOs for queries that only need a subset of data.
6. Use aggregate query results for statistics rather than loading all entities into the application to recompute them.

## 10. Choosing Repository or DatabaseClient?

Not every query needs a full entity.

| Need | Suitable Choice |
|---|---|
| Find, save, or delete an aggregate root by ID | Spring Data R2DBC repository |
| Query by simple properties expressible via method names | Derived query method |
| Return a custom subset of fields | Projection or DTO |
| Complex joins, GROUP BY, COUNT, SUM, or reports | DatabaseClient or custom repository |
| Execute database-specific SQL | DatabaseClient with controlled SQL |
| Transfer data out to an API | Request/response DTO |

Repositories keep standard persistence code readable. DatabaseClient shines when you need SQL control and mapping to a specific read model. Both approaches can coexist in the same application.

For reporting queries, do not force GROUP BY results into an entity just to reuse CRUD repositories. Create a result type tailored to the exact data the query returns.

## 11. Common Misconceptions

**"Every class with @Table is an aggregate root."** Incorrect. @Table describes mapping to a table. Aggregate root is a role in the domain model and consistency boundary.

**"Value objects must live in the same table as the entity."** Not mandatory. They can be embedded in the table or stored as members in a related table. Storage layout alone does not determine identity.

**"DTOs are just renamed entities."** Incorrect. DTOs are designed for transferring data and can contain a subset of fields, combine multiple sources, or use different field names.

**"COUNT/GROUP BY results are entities."** Incorrect when each row only represents a group and lacks business identity. Map them to projections or DTOs.

**"Entities can always be returned directly from REST APIs."** Doing so couples the API tightly to the persistence model and risks leaking internal fields. DTOs help control the API contract.

**"Spring Data R2DBC automatically tracks entity changes like Hibernate."** Incorrect. Spring Data Relational has no persistence context or JPA/Hibernate-style dirty checking.

**"DDD aggregates and SQL aggregates are the same thing."** Incorrect. One refers to a domain boundary; the other refers to computations over sets of rows.

## 12. Key Takeaways

- **Entity:** has a stable identity; state can change while remaining the same domain object.
- **Aggregate root:** an entity acting as the access point and consistency boundary for a DDD aggregate.
- **Value Object:** has no independent identity; defined by its values and usually immutable.
- **DTO:** shapes data to cross a boundary; not necessarily a persistence or domain model.
- **Projection:** fetches only the data needed for reading; can be represented by an interface or DTO.
- **SQL aggregate query result:** data returned from COUNT, SUM, AVG, MIN, MAX, or GROUP BY; usually a read model/DTO rather than an entity.
- In Spring Data R2DBC, repositories fit aggregate persistence; DatabaseClient fits custom SQL and read models.
- Never confuse entities with aggregate roots, value objects with separate tables, or SQL aggregate results with DDD aggregates.
