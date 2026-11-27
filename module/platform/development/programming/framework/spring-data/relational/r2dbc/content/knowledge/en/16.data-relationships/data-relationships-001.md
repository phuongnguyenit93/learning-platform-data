# Representing One-to-One Relationships with Foreign Keys

A one-to-one relationship describes two tables related such that each record on one side is associated with at most one record on the other side. In the relational model, a common way to represent this relationship is to place a foreign key on one table and add a unique constraint (`UNIQUE`) on the foreign key column.

A single foreign key alone is not enough to create a one-to-one relationship. If multiple rows can hold the same foreign key value, that relationship is many-to-one. The `UNIQUE` constraint is what limits each record to being referenced by at most one row in the table containing the foreign key.

In Spring Data Relational R2DBC, it is important to distinguish the relationship structure in the database from the Java object model. R2DBC does not use the JPA `@OneToOne` annotation to automatically create and manage an object graph. The application needs to design foreign keys and constraints in the schema, map the tables to appropriate entities, and then read or write related data using repositories, SQL, or `DatabaseClient` according to aggregate boundaries.

This lesson explains how to choose the placement of the foreign key, how to enforce one-to-one semantics with constraints, how to model entities in Spring Data R2DBC, how to query two tables, and how to maintain consistency when writing or deleting data.

## 1. Meaning of a One-to-One Relationship

Suppose a system manages customers and personal profiles. Each profile belongs to one customer, and each customer has at most one profile.

Two tables:

- `customer`: stores primary customer data.
- `customer_profile`: stores extended profile information.

Example:

~~~text
customer
+----+-------------+
| id | full_name   |
+----+-------------+
| 10 | Nguyen An   |
| 11 | Tran Binh   |
+----+-------------+

customer_profile
+----+------------+----------------+
| id | customer_id| date_of_birth  |
+----+------------+----------------+
| 50 | 10         | 1995-04-12     |
| 51 | 11         | 1990-09-23     |
+----+------------+----------------+
~~~

The `customer_profile.customer_id` column references `customer.id`. If each customer may have at most one profile, this column must have a `UNIQUE` constraint.

A one-to-one relationship typically has two interpretations of optionality:

- **Optional one-to-one:** a customer might not have a profile yet; if they do, there is only one.
- **Unidirectional mandatory one-to-one:** every profile must belong to exactly one customer, and each customer has at most one profile. A customer may still not have a profile yet.

This is a key distinction: a `NOT NULL` foreign key on the child table ensures every child row has a parent row. It does not ensure every parent row has a child row. To require every customer to always have a profile, you need additional business-layer rules or a more suitable data design.

## 2. A Foreign Key Alone Does Not Create a One-to-One Relationship

Suppose the profile table has a foreign key:

~~~sql
CREATE TABLE customer_profile (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    date_of_birth DATE,
    CONSTRAINT fk_profile_customer
        FOREIGN KEY (customer_id) REFERENCES customer(id)
);
~~~

The foreign key constraint ensures `customer_id` must reference a valid customer. However, this schema still allows multiple profile rows to reference the same customer:

~~~text
customer_profile
+----+------------+
| id | customer_id|
+----+------------+
| 50 | 10         |
| 52 | 10         |
+----+------------+
~~~

This is a many-to-one relationship from `customer_profile` to `customer`, because two profiles can belong to customer 10.

To restrict to one profile per customer, add `UNIQUE`:

~~~sql
ALTER TABLE customer_profile
ADD CONSTRAINT uk_profile_customer UNIQUE (customer_id);
~~~

Or declare it when creating the table:

~~~sql
CREATE TABLE customer_profile (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL UNIQUE,
    date_of_birth DATE,
    CONSTRAINT fk_profile_customer
        FOREIGN KEY (customer_id) REFERENCES customer(id)
);
~~~

Now:

- Foreign key ensures a profile cannot point to a non-existent customer.
- `UNIQUE` ensures one customer cannot be referenced by multiple profiles.
- `NOT NULL` ensures every profile row must have a customer.

These three conditions have different meanings and are commonly used together.

## 3. Choosing Which Table Holds the Foreign Key

The foreign key is usually placed on the dependent table or the table whose lifecycle depends on the other table. In the customer and profile example, `customer_profile` is typically the dependent table because a profile has no meaning without being attached to a customer.

### 3.1. Placing the Foreign Key on the Dependent Table

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL
);

CREATE TABLE customer_profile (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL UNIQUE,
    date_of_birth DATE,
    address VARCHAR(300),
    CONSTRAINT fk_profile_customer
        FOREIGN KEY (customer_id) REFERENCES customer(id)
);
~~~

Advantages:

- The main table does not need a nullable column just to point to extended data.
- The dependent table clearly expresses that it requires a parent row.
- The profile can be deleted without deleting the customer, depending on business rules.
- Extended data can be added per module without making the main table overly wide.

With this design, each profile must belong to one customer; a customer may or may not have a profile yet.

### 3.2. Placing the Foreign Key on the Main Table

It is also possible to place `profile_id` on the `customer` table:

~~~sql
CREATE TABLE customer_profile (
    id BIGINT PRIMARY KEY,
    date_of_birth DATE,
    address VARCHAR(300)
);

CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    profile_id BIGINT UNIQUE,
    CONSTRAINT fk_customer_profile
        FOREIGN KEY (profile_id) REFERENCES customer_profile(id)
);
~~~

`UNIQUE(profile_id)` ensures one profile is not used by multiple customers. If `profile_id` is nullable, a customer may not have a profile yet.

Placing the foreign key on the main table can fit when the customer side always owns the reference to the profile. However, you must consider insert order: you must create the profile first to get `profile_id`, and only then create the customer, unless the database supports deferred constraints and the application deliberately uses that feature.

### 3.3. Criteria for Choosing Placement

| Criterion | Foreign key on dependent table | Foreign key on main table |
|---|---|---|
| Example | `profile.customer_id` | `customer.profile_id` |
| Suitable when | Dependent record needs to know its owner | Main record always references auxiliary data |
| Creating data | Create main row first, dependent row second | Usually create referenced row first |
| Deleting auxiliary data | Dependent row can be deleted independently | Must handle reference from main row |
| Expressing optionality | Parent can have no child | Nullable FK allows parent with no reference |
| One-to-one constraint | `UNIQUE` on FK | `UNIQUE` on FK |

Choose placement based on ownership, lifecycle, creation order, and frequent query patterns. Both designs can represent one-to-one if appropriate constraints are present.

## 4. Using the Primary Key as Both Primary Key and Foreign Key

Another design is sharing the primary key value between the main table and the extension table. The child table's primary key is simultaneously a foreign key referencing the parent table.

Example:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL
);

CREATE TABLE customer_profile (
    customer_id BIGINT PRIMARY KEY,
    date_of_birth DATE,
    address VARCHAR(300),
    CONSTRAINT fk_profile_customer
        FOREIGN KEY (customer_id) REFERENCES customer(id)
);
~~~

Here `customer_profile.customer_id` is both primary key and foreign key. Since a primary key is already unique, each customer has at most one profile row.

Advantages:

- No need for an extra separate ID for the profile table.
- The one-to-one relationship is expressed directly via a shared primary key.
- It is impossible to have two profile rows referencing the same customer.

Limitations:

- The profile's key depends on the customer's key.
- Creating a profile requires knowing the customer ID.
- The profile has no identifier independent of the customer.
- If the profile needs to be referenced independently or have its own lifecycle, a separate key can be more flexible.

A shared primary key only ensures each customer has at most one profile; it still does not require every customer to have a profile.

## 5. Optionality, Mandatory Presence, and Uniqueness

Three schema attributes are commonly combined:

| Constraint | Meaning |
|---|---|
| `FOREIGN KEY` | Value must reference a valid row |
| `UNIQUE` | No two rows share the same foreign key value |
| `NOT NULL` | Every row must have a foreign key value |

Example of an optional one-to-one from customer to profile:

~~~sql
customer_id BIGINT UNIQUE
    REFERENCES customer(id)
~~~

The column can be null. When non-null, it must be unique and reference a valid customer.

Example of a mandatory one-to-one for every profile row:

~~~sql
customer_id BIGINT NOT NULL UNIQUE
    REFERENCES customer(id)
~~~

Every profile must have a customer, and each customer has at most one profile.

Note that how multiple `NULL` values are handled in a unique constraint differs across database engines and specific configurations. PostgreSQL normally allows multiple `NULL` values in a unique constraint because null values are treated as not equal; other engines may have different rules or support separate options. Confirm the behavior on your target database.

## 6. Referential Actions on Delete or Update

When a referenced row is deleted or its key is changed, the database needs to know how to handle dependent rows.

Common options:

| Action | Meaning |
|---|---|
| `RESTRICT` / `NO ACTION` | Prevents the operation if referencing rows still exist, depending on database semantics |
| `CASCADE` | Deletes or updates dependent rows along with the referenced row |
| `SET NULL` | Sets the foreign key to null when the referenced row is deleted |
| `SET DEFAULT` | Assigns a default value if supported by the database and that value is valid |

Example using cascade when a profile cannot exist independently of a customer:

~~~sql
CONSTRAINT fk_profile_customer
    FOREIGN KEY (customer_id)
    REFERENCES customer(id)
    ON DELETE CASCADE
~~~

If business rules require retaining profiles for auditing, `CASCADE` may be inappropriate. You can use `RESTRICT` to force the application to handle the profile before deleting the customer.

If the foreign key is nullable and you want to keep the profile row while removing the link:

~~~sql
FOREIGN KEY (customer_id)
    REFERENCES customer(id)
    ON DELETE SET NULL
~~~

However, `SET NULL` is invalid if `customer_id` has `NOT NULL`.

Do not choose cascade just because it is convenient in code. The referential action must reflect retention rules and data lifecycle. The database is the final layer of protection even when a delete operation does not go through Spring Data.

## 7. Mapping Two Tables to Entities in Spring Data R2DBC

Spring Data Relational uses metadata such as `@Table`, `@Id`, and `@Column` to map entities to tables. The foreign key remains a column in the schema; the application can represent the foreign key value as an ID property in the dependent entity.

Example customer entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String fullName;

    // Constructor, getters, and setters
}
~~~

Profile entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer_profile")
public class CustomerProfile {

    @Id
    private Long id;

    @Column("customer_id")
    private Long customerId;

    @Column("date_of_birth")
    private LocalDate dateOfBirth;

    private String address;

    // Constructor, getters, and setters
}
~~~

`customerId` is the foreign key value. It indicates which customer the profile belongs to. This property does not automatically load a related `Customer` object.

Repositories:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}

public interface CustomerProfileRepository
        extends ReactiveCrudRepository<CustomerProfile, Long> {

    Mono<CustomerProfile> findByCustomerId(Long customerId);
}
~~~

Because `customer_id` has a unique constraint, `findByCustomerId` can return `Mono<CustomerProfile>` to represent at most one profile. If the schema does not enforce uniqueness, you should use `Flux<CustomerProfile>` or fix the schema to match the actual one-to-one rule.

### 7.1. Why Use an ID Instead of Declaring an Object Reference?

In Spring Data Relational, do not assume that declaring:

~~~java
private Customer customer;
~~~

will produce behavior like JPA `@OneToOne`, automatically joining on read and automatically saving both tables. Spring Data R2DBC does not provide the JPA ORM model with `@OneToOne`, lazy proxies, and corresponding cascade persistence.

Using `Long customerId` makes the foreign key column explicit and lets the application decide when the customer needs to be loaded. If a combined object is needed, query explicitly and map to a DTO or domain model in the service layer.

### 7.2. Distinguishing Aggregate Root and Dependent Rows

Spring Data Relational encourages aggregate-oriented design. If a profile is data owned by a customer and always shares the same lifecycle as the customer, consider representing them within the same aggregate boundary using the relationship mapping mechanism supported by your Spring Data version.

If the customer and profile have independent lifecycles, ownership, or update workflows, they can be treated as separate aggregates keeping references by ID. In that case, the application coordinates reading and writing both aggregates.

Do not build a large object graph just because two tables share a foreign key. Aggregate boundaries should be based on business invariants and data ownership.

## 8. Querying One-to-One Relationships with Derived Queries

When you only need to read a profile by its foreign key, a derived query is concise:

~~~java
public interface CustomerProfileRepository
        extends ReactiveCrudRepository<CustomerProfile, Long> {

    Mono<CustomerProfile> findByCustomerId(Long customerId);

    Mono<Boolean> existsByCustomerId(Long customerId);
}
~~~

`findByCustomerId` returns at most one profile if `customer_id` has a unique constraint. `existsByCustomerId` only answers whether one exists without loading the full entity.

You can fetch the customer first, then fetch the profile:

~~~java
Mono<CustomerWithProfile> findCustomerDetails(Long customerId) {
    return customerRepository.findById(customerId)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(customerId)))
            .flatMap(customer ->
                    customerProfileRepository.findByCustomerId(customerId)
                            .map(profile ->
                                    CustomerWithProfile.from(customer, profile))
                            .defaultIfEmpty(
                                    CustomerWithProfile.withoutProfile(customer)));
}
~~~

This example treats the profile as optional: the customer is still returned when no profile exists. If a profile is mandatory by business rules, replace `defaultIfEmpty` with `switchIfEmpty(Mono.error(...))`.

Do not call `subscribe()` inside a service to run two separate queries. Compose the publishers and return a single reactive chain so the caller, transaction, and errors are managed consistently.

## 9. Using JOIN and Projections When Combined Data Is Needed

If a screen needs both the customer and profile information, a single join query can be more efficient than two separate reads.

Example DTO:

~~~java
public record CustomerProfileView(
        Long customerId,
        String fullName,
        LocalDate dateOfBirth,
        String address) {
}
~~~

Query using `LEFT JOIN` so customers without a profile are still returned:

~~~sql
SELECT
    c.id AS customer_id,
    c.full_name AS full_name,
    p.date_of_birth AS date_of_birth,
    p.address AS address
FROM customer c
LEFT JOIN customer_profile p
    ON p.customer_id = c.id
WHERE c.id = :customerId;
~~~

When declaring the query in a repository, you can use:

~~~java
@Query("""
    SELECT
        c.id AS customer_id,
        c.full_name AS full_name,
        p.date_of_birth AS date_of_birth,
        p.address AS address
    FROM customer c
    LEFT JOIN customer_profile p
        ON p.customer_id = c.id
    WHERE c.id = :customerId
    """)
Mono<CustomerProfileView> findProfileView(Long customerId);
~~~

`LEFT JOIN` preserves the `customer` row even when there is no `customer_profile`. The profile columns are then SQL `NULL`.

If you use `INNER JOIN`, customers without a profile will not appear in the results. Choose the join type according to the business contract:

| JOIN Type | Result |
|---|---|
| `INNER JOIN` | Only customers with a matching profile |
| `LEFT JOIN` | All customers; profile fields may be null |
| `RIGHT JOIN` | All profiles, even without a corresponding customer; usually unnecessary if FK is enforced |
| `FULL OUTER JOIN` | Keeps rows from both sides; support depends on database |

Because the foreign key guarantees a profile always has a customer, `RIGHT JOIN` or `FULL OUTER JOIN` is usually unnecessary for this model. `LEFT JOIN` is typically appropriate when the profile is optional.

Use clear aliases to avoid column name collisions such as `id`, `created_at`, or `status` when joining multiple tables.

## 10. Querying Combined Data with DatabaseClient

`DatabaseClient` lets you write explicit SQL and map results to a DTO:

~~~java
Mono<CustomerProfileView> findCustomerProfile(Long customerId) {
    return databaseClient.sql("""
            SELECT
                c.id AS customer_id,
                c.full_name AS full_name,
                p.date_of_birth AS date_of_birth,
                p.address AS address
            FROM customer c
            LEFT JOIN customer_profile p
                ON p.customer_id = c.id
            WHERE c.id = :customerId
            """)
            .bind("customerId", customerId)
            .map((row, metadata) -> new CustomerProfileView(
                    row.get("customer_id", Long.class),
                    row.get("full_name", String.class),
                    row.get("date_of_birth", LocalDate.class),
                    row.get("address", String.class)))
            .one();
}
~~~

`one()` is appropriate because `customer.id` is the primary key, so the query returns at most one row. If the customer does not exist, the publisher completes empty. If the customer row exists but there is no profile yet, `date_of_birth` and `address` may be null due to `LEFT JOIN`.

These are two distinct states:

- No customer: no result row.
- Customer exists but no profile: one result row with null profile columns.

If you need to clearly distinguish a missing profile from a profile with nullable fields, also select `p.id AS profile_id`. If `profile_id` is null, no profile row was joined. If the ID is present but a profile attribute is null, the profile exists but that field has no value yet.

## 11. Writing Data in Order and Within a Transaction

When the foreign key resides on `customer_profile`, the customer must exist before inserting the profile:

~~~text
1. INSERT customer
        |
        v
2. Receive customer.id
        |
        v
3. INSERT customer_profile(customer_id, ...)
        |
        v
4. COMMIT
~~~

If both operations must succeed or roll back together, place them inside a reactive transaction.

Conceptual example with `TransactionalOperator`:

~~~java
Mono<CustomerProfile> createCustomerWithProfile(
        Customer customer,
        CustomerProfile profile) {

    return customerRepository.save(customer)
            .flatMap(savedCustomer -> {
                profile.setCustomerId(savedCustomer.getId());
                return customerProfileRepository.save(profile);
            })
            .as(transactionalOperator::transactional);
}
~~~

`transactionalOperator` must be configured with the exact `ConnectionFactory` that the repositories use. If two repositories use different connection factories or a publisher is subscribed separately, they may not participate in the same transaction.

If the profile is optional and a customer can be created first with the profile added later, the two operations can belong to separate use cases. In that case, they do not necessarily need to be combined in a single long transaction.

### 11.1. When the Foreign Key Is on the Main Table

If `customer.profile_id` references `customer_profile.id`, the creation order is usually reversed:

1. Create the profile and obtain its ID.
2. Assign that ID to the customer.
3. Save the customer.

With circular foreign keys or when both sides have mandatory references to each other, inserts can become complicated. Avoid circular designs unless there is a strong business reason; a single foreign key is usually sufficient to represent the relationship.

## 12. Protecting One-to-One Cardinality Under Concurrent Requests

A common mistake is checking that a profile does not exist yet and then inserting:

~~~java
return profileRepository.existsByCustomerId(customerId)
        .flatMap(exists -> {
            if (exists) {
                return Mono.error(
                        new ProfileAlreadyExistsException(customerId));
            }

            return profileRepository.save(profile);
        });
~~~

This logic is useful for producing a friendly business error message, but it does not guarantee uniqueness under concurrent requests:

~~~text
Request A: existsByCustomerId -> false
Request B: existsByCustomerId -> false
Request A: INSERT profile
Request B: INSERT profile
~~~

Without a unique constraint, both can succeed and create two profiles for one customer.

`UNIQUE(customer_id)` in the database is the final line of defense. When two requests race, one insert succeeds; the other insert receives a unique constraint violation error. The application should translate that error into an appropriate business response.

Do not rely on pre-insert existence checks as the sole mechanism. Database constraints enforce the rule even when data is written by batch jobs, scripts, other services, or multiple application instances.

## 13. Deleting and Updating Relationships

Determine what should happen when deleting either a customer or a profile:

- If deleting a customer must delete the profile, consider `ON DELETE CASCADE`.
- If deleting a customer should be prevented while a profile exists, use `RESTRICT`/`NO ACTION` and handle the profile first.
- If deleting a profile while keeping the customer, you can delete the profile row independently when the FK is on the profile table.
- If the FK is on the main table and the profile is deleted, you must update `profile_id` to null or choose an appropriate referential action.

Example deleting a profile by customer ID:

~~~java
Mono<Void> deleteProfile(Long customerId) {
    return profileRepository.deleteByCustomerId(customerId);
}
~~~

If the database has `ON DELETE CASCADE`, deleting a customer can automatically delete the dependent profile. Even so, the application must clearly understand the impact of the delete statement and test it on the target database.

For data requiring auditing, historical retention, or regulatory compliance, soft delete or an archived status may be needed instead of physical/cascade deletion.

## 14. Schema Migration and Existing Data

Adding a `UNIQUE` constraint to a table that already contains data can fail if multiple rows already share the same `customer_id`.

Before migrating, detect duplicate data:

~~~sql
SELECT customer_id, COUNT(*) AS profile_count
FROM customer_profile
GROUP BY customer_id
HAVING COUNT(*) > 1;
~~~

Duplicate groups must be resolved according to business rules: select a record to keep, merge data, move historical data to a separate table, or require administrator resolution. Never randomly delete a row just to make the migration pass.

Once the data is clean, create the constraint:

~~~sql
ALTER TABLE customer_profile
ADD CONSTRAINT uk_profile_customer UNIQUE (customer_id);
~~~

If the column is required, verify there are no nulls before setting `NOT NULL`:

~~~sql
SELECT COUNT(*)
FROM customer_profile
WHERE customer_id IS NULL;
~~~

Manage changes with Flyway, Liquibase, or your project's migration tool. Entity annotations do not automatically create foreign keys or unique constraints in production schemas.

## 15. Common Mistakes

| Mistake | Consequence | How to Handle |
|---|---|---|
| Creating only a foreign key without `UNIQUE` | One customer can have multiple profiles | Add `UNIQUE` on the FK column |
| Thinking `NOT NULL` ensures every customer has a profile | It only ensures every profile row has a customer | Add business rules or change the model |
| Placing the FK on the side that is hard to create first | Causes insert order dependencies or FK cycles | Place the FK based on ownership and lifecycle |
| Using JPA `@OneToOne` on R2DBC entities | The annotation does not provide JPA mapping in Spring Data Relational | Map the FK column explicitly and query related data explicitly |
| Declaring an object reference and expecting auto-join | It may not be materialized as expected | Use FK ID, projections, and explicit JOINs |
| Returning `Mono<Profile>` when FK is not unique | Multi-row data can fail single-result queries | Add a constraint or use `Flux` if truly many-to-one |
| Checking `exists` before inserting without a constraint | Concurrent requests can create duplicate rows | Use a unique constraint and handle violation errors |
| Using `INNER JOIN` for an optional relationship | Customers without a profile are excluded from results | Use `LEFT JOIN` |
| Not distinguishing a missing row from null columns | Response may misinterpret the state | Select the auxiliary row's ID to determine whether it exists |
| Deleting parent without defining FK behavior | Delete fails or cascades unexpectedly | Choose `RESTRICT`, `CASCADE`, or `SET NULL` per business rules |
| Writing two tables without a transaction | One table may be written when the other fails | Use a reactive transaction when atomicity is required |
| Adding `UNIQUE` to legacy data with duplicates | Migration fails | Check and resolve duplicates before migration |

## 16. One-to-One Relationship Design Workflow

When modeling two tables with a one-to-one relationship, follow this sequence:

1. Identify which record is the primary subject and which depends on it by lifecycle or business rules.
2. Choose which table holds the foreign key; favor placement that makes create, update, and delete flows clear.
3. Add a foreign key to prevent references to non-existent records.
4. Add `UNIQUE` or use a shared primary key to guarantee at most one row on the dependent side.
5. Decide whether the foreign key is `NOT NULL` or nullable.
6. Define `ON DELETE` and `ON UPDATE` behavior according to data policy.
7. Map each table to a separate entity with `@Table`, `@Id`, and `@Column`.
8. Keep the foreign key as an explicit ID property when referencing across aggregates.
9. Use derived queries for separate reads or `JOIN`/projections when combined data is needed.
10. Use a reactive transaction for multi-table operations requiring atomicity.
11. Handle unique constraint errors to protect against concurrent requests.
12. Write migrations and integration tests against the actual database and driver.

## 17. Key Takeaways

- A one-to-one relationship requires a foreign key plus a `UNIQUE` constraint on the FK column, or a shared primary key.
- A foreign key ensures valid references; `UNIQUE` limits each row to being referenced at most once; `NOT NULL` requires every row to have an FK value.
- `NOT NULL` on the child table does not guarantee that every parent row has a child row.
- The FK can be placed on either the dependent table or the main table; choose based on ownership, lifecycle, and data creation order.
- Spring Data R2DBC does not use JPA's `@OneToOne` to automatically create relationships, joins, lazy loading, or cascades.
- Mapping the FK as an explicit ID property is a clear way to reference another aggregate.
- Use `LEFT JOIN` when the main record must still appear if auxiliary data does not yet exist.
- Use reactive transactions when creating or updating two tables must succeed or roll back together.
- Enforce uniqueness with a database unique constraint; pre-insert existence checks do not prevent race conditions.
- Migrations must clean up existing duplicate and null values before adding constraints.
- Test cases with auxiliary records, without auxiliary records, invalid FKs, duplicates, and deletes according to the chosen policy.
