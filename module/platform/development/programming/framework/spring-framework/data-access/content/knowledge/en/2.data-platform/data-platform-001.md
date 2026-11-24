# Tables, Rows, Columns, and Their Relationship with Java Objects

In a Java application using the Spring Framework to access a relational database, you need to understand two ways of organizing data: the **relational model** in the database and the **object model** in Java. One side stores data using tables, rows, columns, and keys; the other represents data using classes, objects, fields, and relationships between objects. The two models are closely related, yet not identical.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish between a table, a row/record, a column, a cell, a schema, and SQL data types.
- Explain primary keys, foreign keys, constraints, and one-to-one, one-to-many, and many-to-many relationships.
- Map a SQL row to a Java object, and understand the roles of DTOs, entities, JDBC `ResultSet`, and Spring `RowMapper`.
- Understand why `JOIN` produces multiple result rows and how to group data into an object containing a collection.
- Recognize the difference between a Java object reference and a database foreign key, and choose safe ways to read and write data.

## 2. What Are Tables, Rows, and Columns Really?

Consider the **customer** table:

| customer_id | full_name | email |
| ---: | --- | --- |
| 1 | An | an@example.com |
| 2 | Binh | binh@example.com |

- A **table** is a set of rows sharing the same column structure, such as `customer`. The table name identifies a kind of data according to the domain design.
- A **column** is an attribute with a name and data type defined in the schema: `customer_id BIGINT`, `full_name VARCHAR(100)`, `email VARCHAR(255)`.
- A **row** is a record containing values for the table's columns. The row `(1, 'An', 'an@example.com')` describes one customer.
- A **cell** is the value at the intersection of a row and a column; `'An'` is the value of the `full_name` column in the row with `customer_id = 1`.
- A **schema** describes table structures, column types, keys, and constraints. The actual data consists of the rows stored under that schema.

A table is not synonymous with a Java array; a database manages persistent data, queries over sets, enforces constraints, and coordinates concurrent transactions. Row order is **not guaranteed** if a query has no `ORDER BY`. A `SELECT` result may contain fewer or more columns than the underlying table, or columns computed from expressions.

### Data Types and NULL Values

SQL types help the database validate, store, and process values. For example, `VARCHAR(100)` stores length-limited text, `BIGINT` stores large integers, `DECIMAL(12,2)` stores exact decimal numbers with the specified precision and scale, and `TIMESTAMP` stores date-time instants (time zone semantics depend on the specific type and database management system).

**SQL NULL** represents an unknown or missing value; it differs from an empty string `''`, the number `0`, and the boolean `false`. Comparing with `= NULL` does not work as intended; use `IS NULL` or `IS NOT NULL`. Expressions involving `NULL` generally follow three-valued logic (true/false/unknown), so you must pay attention when filtering data with `WHERE`.

For example, `email VARCHAR(255) NOT NULL` requires a non-NULL value, though by itself it does not validate email syntax; separate domain validation is needed.

## 3. Sample Table Design and Constraints

We use three tables: customer, purchase order, and order line item. The following SQL illustrates a structure compatible with databases supporting common syntax such as PostgreSQL and H2; DDL details may vary by DBMS.

~~~sql
CREATE TABLE customer (
    customer_id BIGINT PRIMARY KEY,
    full_name   VARCHAR(100) NOT NULL,
    email       VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE purchase_order (
    order_id     BIGINT PRIMARY KEY,
    customer_id  BIGINT NOT NULL,
    created_at   TIMESTAMP NOT NULL,
    status       VARCHAR(20) NOT NULL,
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id) REFERENCES customer(customer_id),
    CONSTRAINT ck_order_status
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);

CREATE TABLE order_item (
    order_item_id BIGINT PRIMARY KEY,
    order_id      BIGINT NOT NULL,
    product_name  VARCHAR(150) NOT NULL,
    quantity      INTEGER NOT NULL CHECK (quantity > 0),
    unit_price    DECIMAL(12,2) NOT NULL CHECK (unit_price >= 0),
    CONSTRAINT fk_item_order
        FOREIGN KEY (order_id) REFERENCES purchase_order(order_id)
);
~~~

Meaning:

- **`PRIMARY KEY`** uniquely identifies each row; it cannot contain duplicates and cannot be NULL. In this example, the key is a single column. In practice, **composite keys** spanning multiple columns also exist.
- **`FOREIGN KEY`** is a referential constraint: `purchase_order.customer_id` must reference an existing `customer.customer_id`, unless the column allows NULL. A foreign key **does not automatically create a Java object**.
- **`NOT NULL`** forbids SQL NULL; **`UNIQUE`** requires unique values according to the database's rules; **`CHECK`** evaluates a condition in the database.
- **`DEFAULT`** (if declared) supplies a value when an INSERT omits the corresponding column, according to SQL/database rules.
- **Indexes** speed up certain lookups and joins, at the cost of storage space and write overhead; primary and unique keys are typically enforced via index structures, depending on the database. A foreign key is not guaranteed to automatically create an index on the referencing column.

Sample data can be inserted:

~~~sql
INSERT INTO customer (customer_id, full_name, email) VALUES
    (1, 'An', 'an@example.com'),
    (2, 'Binh', 'binh@example.com');

INSERT INTO purchase_order (order_id, customer_id, created_at, status) VALUES
    (100, 1, '2026-10-01 09:00:00', 'NEW'),
    (101, 1, '2026-10-02 10:30:00', 'PAID');

INSERT INTO order_item (order_item_id, order_id, product_name, quantity, unit_price) VALUES
    (1000, 100, 'Book', 2, 120000.00),
    (1001, 100, 'Pen', 1, 10000.00),
    (1002, 101, 'Notebook', 3, 15000.00);
~~~

Because keys are assigned manually in this example, when designing a real system you should choose an appropriate ID generation mechanism (identity/sequence/UUID or another strategy) to avoid key collisions and handle errors under concurrent writes.

## 4. Keys Represent Relationships Between Rows

The model above has these relationships:

~~~mermaid
erDiagram
    CUSTOMER ||--o{ PURCHASE_ORDER : places
    PURCHASE_ORDER ||--o{ ORDER_ITEM : contains
    CUSTOMER {
        BIGINT customer_id PK
        VARCHAR full_name
        VARCHAR email
    }
    PURCHASE_ORDER {
        BIGINT order_id PK
        BIGINT customer_id FK
        TIMESTAMP created_at
        VARCHAR status
    }
    ORDER_ITEM {
        BIGINT order_item_id PK
        BIGINT order_id FK
        VARCHAR product_name
        INTEGER quantity
        DECIMAL unit_price
    }
~~~

**One-to-many (1:N):** A customer can have many orders, yet each `purchase_order` in this design belongs to exactly one customer. An order has many order items. In the sample schema, the database allows an order without any items; requiring at least one item demands appropriate business/transactional rules.

**One-to-one (1:1):** For example, a `customer_profile` table whose `customer_id` is both its primary key and a foreign key to `customer`. Then each customer has at most one profile; enforcing that every customer must have a profile requires a separate mechanism, not just a foreign key on the profile side.

**Many-to-many (N:M):** For example, students enroll in many courses and each course has many students. Relational databases typically use a join table `enrollment(student_id, course_id, enrolled_at)` with two foreign keys. The pair `(student_id, course_id)` can serve as a composite primary key to prevent duplicate links. Do not assume an ordinary SQL column can natively store a `List<Course>`.

**Referential integrity:** You cannot insert an order with `customer_id = 999` when customer 999 does not exist, because the foreign key rejects it. When deleting a referenced customer, the outcome depends on the `ON DELETE` policy (the default usually prevents deletion; `CASCADE`/`SET NULL` can be configured by design). Do not infer deletion behavior from Java annotations alone.

## 5. From SQL Rows to Java Objects

The correspondence is intuitive, though only a convention:

| Database | Java | What to Watch For |
| --- | --- | --- |
| Table `customer` | Class/record `Customer` | One table does not have to correspond to exactly one class |
| One row of `customer` | One `Customer` instance | One object can combine data from multiple tables |
| Column `full_name` | Field/component `name` | Names differ, requiring explicit mapping |
| Primary key `customer_id` | Field `id` | A database ID is different from an object's memory address |
| Foreign key `customer_id` | Field `customerId` or reference `customer` | Choose based on the model and access technology |
| Multiple related rows | `List<Order>`, `Set<Order>` | Requires a query/join/ORM to fetch the data |
| SQL NULL | `null` or modeling by data type | Primitives `long`/`int` cannot hold null |

Java 17+ example for **data transfer objects / DTOs**:

~~~java
import java.time.LocalDateTime;

record Customer(long id, String name, String email) {}

record PurchaseOrder(
        long id,
        long customerId,
        LocalDateTime createdAt,
        String status
) {}
~~~

These are valid Java data types; they only describe in-memory objects and **do not automatically connect to or create tables**. `Customer` uses the component `name` while the database column is named `full_name`; the mapping layer must decide that these two names correspond. `PurchaseOrder.customerId` stores the foreign key as an integer, not the `Customer` object itself; obtaining the customer requires querying and assembling the result or using an ORM.

**A Java reference is not a foreign key:** A variable `Customer customer` holds a reference to an object in JVM memory. A column `customer_id BIGINT` stores an identifier value. An ORM can map a reference to a foreign key, yet that is behavior of the mapping/persistence layer, not the inherent nature of a Java variable.

**Object identity vs. row identity:** `a == b` on two Java references checks whether they are the same instance; `customer_id` checks whether they represent the same logical record in the database. Two distinct Java object instances can carry the same ID `1`. Defining `equals/hashCode` for an entity requires considering ungenerated IDs, proxies, and collections; do not equate them mechanically.

### Common SQL Types and Their Java Counterparts

| SQL | Common Java Type | Notes |
| --- | --- | --- |
| `INTEGER` | `int` / `Integer` | Use the wrapper when the column is nullable |
| `BIGINT` | `long` / `Long` | `getLong()` returns 0 on SQL NULL; check `wasNull()` if needed |
| `VARCHAR`, `TEXT` | `String` | SQL NULL can still become Java `null` |
| `DECIMAL(p,s)` | `BigDecimal` | Suitable for money/exact numbers; avoid `double` when decimal precision matters |
| `BOOLEAN` | `boolean` / `Boolean` | Depends on nullability and the driver |
| `DATE` | `LocalDate` | Date only, without time |
| `TIMESTAMP` without time zone | `LocalDateTime` | Does not carry a time zone itself; mapping depends on the driver |
| `TIMESTAMP WITH TIME ZONE` | `OffsetDateTime` or a driver-supported mapping | Semantics and retrieval behavior vary by database/driver |

These are common mappings, not a guarantee that every JDBC driver supports every `ResultSet.getObject(column, Type.class)` call or identical conversion behavior. When working with timestamps, align column types, time zones, and display rules.

## 6. SQL Returns Result Rows, Not Object Graphs

Using the sample data:

~~~sql
SELECT c.customer_id, c.full_name, o.order_id, o.status
FROM customer AS c
JOIN purchase_order AS o
  ON o.customer_id = c.customer_id
WHERE c.customer_id = 1
ORDER BY o.order_id;
~~~

Result:

| customer_id | full_name | order_id | status |
| ---: | --- | ---: | --- |
| 1 | An | 100 | NEW |
| 1 | An | 101 | PAID |

**Two result rows do not mean two customers.** `JOIN` combines matching rows, so the `customer` data repeats for each order. An application that wants to display a single customer object containing a list of orders must **group by the key** `customer_id`; it must not create two customer objects and treat them as two separate domain entities.

For a customer with no orders, `INNER JOIN` produces no rows. `LEFT JOIN` still returns the customer and sets the order-side columns to NULL:

~~~sql
SELECT c.customer_id, c.full_name, o.order_id
FROM customer AS c
LEFT JOIN purchase_order AS o
  ON o.customer_id = c.customer_id
WHERE c.customer_id = 2;
~~~

The result has one row `(2, 'Binh', NULL)`. When mapping to Java, the `orderId` field must be able to represent NULL (for example `Long`), or the mapper must detect that there is no order. When joining `order_item` as well, an order can appear multiple times; if collecting a list of orders, deduplicate by `order_id` before adding items.

### Standalone Java 17+: Grouping JOIN Rows into Nested Objects

This simulates `JOIN` rows already read from a database. The example uses plain Java to clarify the **row → object graph** step without needing JDBC or Spring. Save it to `MappingDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record JoinedRow(long customerId, String customerName,
                 long orderId, String status) {}
record OrderView(long id, String status) {}
record CustomerOrders(long id, String name, List<OrderView> orders) {}

public class MappingDemo {
    public static void main(String[] args) {
        List<JoinedRow> rows = List.of(
                new JoinedRow(1, "An", 100, "NEW"),
                new JoinedRow(1, "An", 101, "PAID")
        );

        Map<Long, String> names = new LinkedHashMap<>();
        Map<Long, List<OrderView>> ordersByCustomer = new LinkedHashMap<>();

        for (JoinedRow row : rows) {
            names.putIfAbsent(row.customerId(), row.customerName());
            ordersByCustomer
                    .computeIfAbsent(row.customerId(), k -> new ArrayList<>())
                    .add(new OrderView(row.orderId(), row.status()));
        }

        for (Map.Entry<Long, String> entry : names.entrySet()) {
            long customerId = entry.getKey();
            CustomerOrders customer = new CustomerOrders(
                    customerId,
                    entry.getValue(),
                    List.copyOf(ordersByCustomer.get(customerId))
            );

            String ids = customer.orders().stream()
                    .map(order -> Long.toString(order.id()))
                    .collect(Collectors.joining(", "));
            System.out.println(
                    customer.name() + " has " + customer.orders().size()
                            + " orders: " + ids
            );
        }
    }
}
~~~

Run:

~~~bash
javac MappingDemo.java
java MappingDemo
~~~

Exact stdout:

~~~text
An has 2 orders: 100, 101
~~~

`LinkedHashMap` preserves encounter order in this example, `computeIfAbsent` creates a list for an unseen ID, and `List.copyOf` creates an unmodifiable copy of the list. With real queries, you also need to account for customers with no orders, NULL records, duplicate orders when joining multiple tables, and memory cost if results are very large.

## 7. Spring JDBC: Turning a ResultSet into Objects with RowMapper

When using JDBC, a SQL statement produces a `ResultSet`. The result cursor is iterated row by row; each row contains column values read by name or position. With Spring JDBC, `JdbcTemplate` handles most of obtaining connections, preparing/executing statements, and closing resources; `RowMapper<T>` converts **one result row** into one `T` object.

The following example is for a Spring application already configured with a `DataSource` and the `spring-jdbc` dependency. Save it as `CustomerRepository.java` in the corresponding package of your project:

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class CustomerRepository {
    public record CustomerDto(long id, String name, String email) {}

    private final JdbcTemplate jdbc;

    public CustomerRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<CustomerDto> findById(long customerId) {
        List<CustomerDto> rows = jdbc.query(
                """
                SELECT customer_id, full_name, email
                FROM customer
                WHERE customer_id = ?
                """,
                (rs, rowNum) -> new CustomerDto(
                        rs.getLong("customer_id"),
                        rs.getString("full_name"),
                        rs.getString("email")
                ),
                customerId
        );

        return rows.stream().findFirst();
    }
}
~~~

How to read the example:

1. `WHERE customer_id = ?` uses a **bound parameter**; Spring/JDBC passes `customerId` as data instead of concatenating user input directly into SQL.
2. When the query returns results, the `RowMapper` lambda reads each column and constructs a `CustomerDto`. `rowNum` is the row index in the callback (0-based), unused here.
3. `jdbc.query(...)` returns `List<CustomerDto>`; `findFirst()` returns `Optional.empty()` if nothing is found. The primary key guarantees at most one matching row when data is valid.
4. Because all example columns are `NOT NULL`, using `long` and `String` directly is appropriate. If an ID is nullable, do not read it with `getLong` and silently treat 0 as a real value.

For writes, Spring JDBC can use `jdbc.update("INSERT INTO customer (...) VALUES (?, ?, ?)", id, name, email)`. The return value indicates the number of affected rows; exceptions from unique/foreign key/check constraints still must be handled. `RowMapper` maps individual rows and does not automatically assemble child lists or perform cascades.

`BeanPropertyRowMapper` can be used when naming conventions and data types align, but explicit mapping is usually clearer for important DTOs or when column names differ from field names. Do not assume column names and Java property names automatically match in every case.

## 8. ORM/JPA: Mapping Tables to Entities and Object Relationships

ORM (Object–Relational Mapping) provides a mapping layer between Java objects and SQL tables. With JPA, a class annotated with `@Entity` can represent a persistent entity; a field with `@Id` corresponds to its identifier, `@Column` customizes the column name, and `@ManyToOne`/`@OneToMany` describe object associations.

Examples of **illustrative declarations** for the same relationships, using annotations from `jakarta.persistence`:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer")
class CustomerEntity {
    @Id
    @Column(name = "customer_id")
    Long id;

    @Column(name = "full_name", nullable = false)
    String fullName;

    protected CustomerEntity() {}
}

@Entity
@Table(name = "purchase_order")
class PurchaseOrderEntity {
    @Id
    @Column(name = "order_id")
    Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    CustomerEntity customer;

    protected PurchaseOrderEntity() {}
}
~~~

This is a mapping example to place in a project with a Jakarta Persistence provider and configured entity scanning; it is not a standalone runnable Java program. The `purchase_order.customer_id` column remains a **SQL foreign key**; the `PurchaseOrderEntity.customer` object is the Java way of accessing that relationship. `@JoinColumn` specifies the join column name; the database needs matching schema/constraints managed via migrations or intentionally configured schema generation.

Key points:

- **An entity is not synonymous with a DTO.** An entity has a persistence context lifecycle, managed/detached states, and dirty-checking synchronization; a DTO/record is usually just data returned or passed between layers. Ordinary Java records suit DTOs; do not treat records as portable JPA entities across providers.
- **`LAZY`** expresses the intent to load an association on demand, though the exact query timing depends on the provider and context. Accessing an association outside an appropriate persistence context/transaction can fail because the data has not been loaded.
- **N+1 queries:** Fetching N orders and touching `order.customer` for each order can trigger many extra queries. Consider `JOIN FETCH`, entity graphs, projections, or tailored queries based on actual needs.
- **Cascade and fetch are two separate concepts.** Fetch determines data loading; cascade determines propagation of persistence operations. Do not enable cascade deletion indiscriminately, as it can delete related data unintentionally.
- **Annotations do not replace SQL understanding.** A `List<PurchaseOrderEntity>` field may involve multiple rows, foreign keys, and separate queries; it does not turn into a list-typed SQL column merely by appearing in a class.

If you use Spring Data JDBC, its mapping and aggregate strategy differs from JPA; do not assume the same lazy loading, proxies, or entity relationships apply. Whichever library you choose, inspect the actual schema and SQL to understand how data is read and written.

## 9. Choosing Data Shapes for Read/Write Needs

| Need | Suitable Approach |
| --- | --- |
| Customer list page | Query only the columns needed for display, return `List<CustomerDto>` |
| View one customer by ID | `Optional<CustomerDto>` or equivalent result when absent |
| View a customer with orders | Join + row grouping; or sensible multiple queries; or controlled ORM mapping |
| Create an order and line items | Write multiple tables in the same transaction, respecting foreign keys |
| Return JSON for an API | Usually use DTOs/projections to control payload, avoid exposing full entities or cyclic relationships |

Choosing **a single join query** versus **multiple queries** depends on data volume, pagination, selectivity, indexes, and display requirements. A 1:N join multiplies rows, making pagination by customer incorrect if `LIMIT` is applied directly to the joined row set. For large datasets, paginate parent entity IDs first and then fetch matching children, or use a controlled retrieval strategy.

## 10. Reading, Writing, and Data Consistency

A typical Spring application flow is:

~~~text
HTTP / job / message
        |
        v
Service (business logic, transaction)
        |
        v
Repository / JDBC / JPA
        |
        v
SQL query + database constraints
        |
        v
Rows / ResultSet -> DTO or entity -> business result
~~~

For example, creating one `purchase_order` and two `order_item` rows: all three writes should be handled as one business unit when atomicity is needed. In Spring, `@Transactional` on an appropriate service can instruct the transaction manager to commit everything on success or roll back on matching exceptions; you must configure a transaction manager and understand rollback rules, self-invocation, and specific transaction boundaries. Foreign keys prevent items from pointing to a nonexistent order, but they do not replace transactions to prevent partially written state.

SQL processes data in sets. Statements like `UPDATE purchase_order SET status = 'PAID' WHERE order_id = ?` affect rows matching the condition; the affected row count should be checked when business logic requires exactly one row. Under concurrent updates, read-then-write alone does not prevent lost updates; optimistic locking (version), appropriate locks, or a suitable isolation level may be required.

Database constraints are the final line of defense for shared data; Java validation helps report clear errors earlier. Both serve complementary purposes.

## 11. Common Mistakes and How to Avoid Them

1. **Confusing rows with objects:** `JOIN` returns two rows for customer An, leading you to think there are two customers. Group by the identifier key and understand query cardinality.
2. **Assuming field name = column name:** `full_name` does not automatically equal `name`. Use explicit mapping or a configured, tested naming convention.
3. **Equating a foreign key with an object reference:** `customer_id` is just a value; a `Customer` object must be loaded, mapped, and have its lifecycle managed if needed.
4. **Ignoring NULL:** Using primitives for nullable columns, or comparing `= NULL`, leads to wrong results. Check the schema and how JDBC APIs handle NULL.
5. **Using floating-point for money:** `double` can introduce binary rounding errors; prefer `DECIMAL` in SQL and `BigDecimal` in Java when exact precision is needed.
6. **Concatenating input into SQL strings:** Risks SQL injection and quoting bugs. Use prepared statements / parameterized queries via JDBC/`JdbcTemplate`.
7. **Omitting keys and constraints:** Duplicate data, orphan orders, or negative quantities can enter the database. Design appropriate PK, FK, UNIQUE, NOT NULL, and CHECK constraints.
8. **Traversing ORM relationships carelessly:** Causes N+1 queries, lazy initialization errors, or loading too many records. Inspect executed SQL and choose queries/projections per use case.
9. **Assuming query results have a default order:** Without `ORDER BY`, do not rely on returned row order.
10. **Forgetting transactions for multi-table writes:** A failure midway through a sequence of writes can leave incomplete data without a properly scoped transaction.
11. **Returning entities directly from an API:** Can pull in circular references, sensitive fields, or uncontrollable lazy loading. Use DTOs for clear API contracts.
12. **Believing every association is automatically persisted:** Creating a Java object with `List<Order>` is not enough to create SQL rows; persistence depends on repositories, mappings, cascades, and transactions.

## 12. Self-Check

**Question 1.** The `customer` table has 2 rows and `purchase_order` has 2 rows, both belonging to customer 1. How many rows does an `INNER JOIN` on `customer_id` produce?  
**Answer:** 2 rows. Customer 2 has no orders and does not appear; customer 1's information repeats twice.

**Question 2.** Why is the column `purchase_order.customer_id` not equivalent to `CustomerEntity customer`?  
**Answer:** The column stores a foreign key value enforced by the database; the Java field is an in-memory object reference. The persistence layer needs proper mapping and loading/saving to bridge the two sides.

**Question 3.** If a column `discount_amount DECIMAL(12,2)` allows NULL, which Java type should you consider?  
**Answer:** `BigDecimal` with `null` support and explicit business rules; do not use `double` just because the value is a decimal number.

**Question 4.** To find customers with no orders, is `INNER JOIN` enough?  
**Answer:** No. You can use `LEFT JOIN` and filter `o.order_id IS NULL`, or use `NOT EXISTS` to identify customers without related rows.

**Question 5.** When creating an order first and then its items, what mechanism prevents a partially saved order if the second operation fails?  
**Answer:** A transaction spanning the sequence of operations, working alongside PK/FK/CHECK constraints and proper error handling.

## 13. Key Takeaways

**Tables, columns, and rows are the database's storage and query structures; classes, fields, and objects are Java's data and behavior structures.** Primary keys identify records, foreign keys link records, and JDBC/Spring/JPA perform the translation between data rows and objects. Understanding cardinality, NULL, data types, JOIN queries, and transactions forms the foundation for reading and writing data correctly before diving deeper into Spring's data access mechanisms.