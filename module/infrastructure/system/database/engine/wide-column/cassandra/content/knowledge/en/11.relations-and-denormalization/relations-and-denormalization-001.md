# Representing One-to-One, One-to-Many, and Many-to-Many Relationships in Apache Cassandra

## Learning Objectives

After this lesson, you will be able to:

- Identify **one-to-one (1:1)**, **one-to-many (1:N)**, and **many-to-many (N:M)** relationships in a business domain model.
- Translate each relationship into Cassandra tables that serve **specific queries**, rather than mechanically copying a relational schema.
- Choose an appropriate `PRIMARY KEY`, **partition key**, and **clustering column** aligned with data access patterns; recognize when a partition might grow too large.
- Explain why data duplication is required, how to update multiple tables at the application layer, and how to handle temporarily out-of-sync replicas.

## 1. Relationship Design Mindset in Cassandra

In relational databases, we usually normalize into tables such as `users`, `orders`, and `order_items`, using **foreign keys** to link them and `JOIN` to combine data at read time. Apache Cassandra is a distributed database following the *wide-column* model: data is distributed based on the **partition key** and is typically designed around the **queries to be served**. Cassandra does not support `JOIN`, foreign keys, or cascading deletes (`ON DELETE CASCADE`) the way an RDBMS does.

Therefore, a business relationship can be represented by **one table**, **two tables**, or multiple **query-specific view tables**. These tables may intentionally duplicate data (*denormalization*). The application is responsible for keeping the representations consistent with one another.

For example, before designing a customer–order relationship, write down the queries that need to run:

1. Fetch customer details by `customer_id`.
2. List the 20 most recent orders of a customer within a month.
3. Look up a single order directly by `order_id`.

Queries (2) and (3) have two different lookup keys. In practice, **two order tables** are usually required so each query reads efficiently, avoiding scanning all data and filtering in the application or relying on `ALLOW FILTERING`.

### Distinguishing the Two Parts of a Primary Key

```sql
PRIMARY KEY ((customer_id, order_month), ordered_at, order_id)
--            ^ partition key              ^ clustering columns
```

- **Partition key** `(customer_id, order_month)` determines the data partition, helping Cassandra route queries to the right set of nodes. To read a specific partition, you normally must provide all partition key components.
- **Clustering columns** `ordered_at`, `order_id` identify rows within the partition and define their storage order. They are very useful when listing records chronologically.
- **Primary key** uniquely identifies a row. Writing again with the same primary key performs an *upsert* on that row; changing any primary key component effectively writes a different row.

Do not equate a **business relationship** with a **foreign key**: the ID values in the examples below express logical links, but Cassandra does not automatically verify whether the referenced object exists.

## 2. One-to-One (1:1) Relationship: Users and Personal Preferences

**Problem:** each user has at most one set of preferences (`locale`, `time_zone`, `email_notifications`). Two common design patterns:

**Approach A — Co-locate in a single row** if the application almost always reads user details and preferences together:

```sql
CREATE TABLE users_with_preferences_by_id (
    user_id uuid PRIMARY KEY,
    display_name text,
    locale text,
    time_zone text,
    email_notifications boolean
);

SELECT display_name, locale, time_zone
FROM users_with_preferences_by_id
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

A single `user_id` lookup retrieves all needed data. However, when preferences have their own lifecycle, require separate access control, or are updated by another service, Approach B can be chosen.

**Approach B — Split into two tables using the same identifier:**

```sql
CREATE TABLE users_by_id (
    user_id uuid PRIMARY KEY,
    display_name text,
    email text
);

CREATE TABLE user_preferences_by_id (
    user_id uuid PRIMARY KEY,
    locale text,
    time_zone text,
    email_notifications boolean
);

INSERT INTO users_by_id (user_id, display_name, email)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'Lan', 'lan@example.com'
);

INSERT INTO user_preferences_by_id
    (user_id, locale, time_zone, email_notifications)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'vi-VN', 'Asia/Ho_Chi_Minh', true
);

SELECT locale, time_zone, email_notifications
FROM user_preferences_by_id
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

In Approach B, `user_preferences_by_id` allows **at most one row per `user_id`**, because `user_id` is the entire primary key. However, Cassandra **does not guarantee** that every row in `users_by_id` has a preferences row, nor does it prevent the application from creating preferences for an ID that has no user. If both need to be displayed, the application reads both tables and joins them by ID.

**Selection rule:** use one row for data always read together and of reasonable size; use two tables when independent reads, access control, or lifecycle management are needed. Do not split tables solely because an entity diagram shows a 1:1 relationship.

## 3. One-to-Many (1:N) Relationship: Customers and Orders

**Problem:** a customer has many orders. Requirements:

- Retrieve the list of most recent orders by customer and by month.
- Find any order by `order_id` (e.g., via an order detail page).

We create two tables for the two read paths:

```sql
-- List of orders for a customer in a given month.
CREATE TABLE orders_by_customer_month (
    customer_id uuid,
    order_month date,
    ordered_at timestamp,
    order_id uuid,
    total_amount decimal,
    order_status text,
    PRIMARY KEY ((customer_id, order_month), ordered_at, order_id)
) WITH CLUSTERING ORDER BY (ordered_at DESC, order_id ASC);

-- Direct lookup of an order by ID.
CREATE TABLE orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    ordered_at timestamp,
    order_month date,
    total_amount decimal,
    order_status text
);
```

`order_month` is the first day of the month, such as `2026-11-01`, computed at order creation time under a consistent application time convention (e.g., UTC). The composite partition key `(customer_id, order_month)` avoids cramming a customer's entire order history into an unbounded partition. The `order_id` key following `ordered_at` distinguishes orders created at the exact same timestamp.

```sql
-- An order creation event is written to both tables.
INSERT INTO orders_by_id
    (order_id, customer_id, ordered_at, order_month,
     total_amount, order_status)
VALUES (
    22222222-2222-4222-8222-222222222222,
    11111111-1111-4111-8111-111111111111,
    '2026-11-21T01:00:00Z', '2026-11-01',
    199000.00, 'PAID'
);

INSERT INTO orders_by_customer_month
    (customer_id, order_month, ordered_at, order_id,
     total_amount, order_status)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-01', '2026-11-21T01:00:00Z',
    22222222-2222-4222-8222-222222222222,
    199000.00, 'PAID'
);

-- 20 most recent orders in November for the customer.
SELECT order_id, ordered_at, total_amount, order_status
FROM orders_by_customer_month
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11-01'
LIMIT 20;

-- Read order details by ID.
SELECT * FROM orders_by_id
WHERE order_id = 22222222-2222-4222-8222-222222222222;
```

This is **intentional denormalization**: `order_status`, `total_amount`, and identifying fields appear in both tables so each read path is efficient. If the status changes from `PAID` to `SHIPPED`, the application must update **both**:

```sql
UPDATE orders_by_id
SET order_status = 'SHIPPED'
WHERE order_id = 22222222-2222-4222-8222-222222222222;

UPDATE orders_by_customer_month
SET order_status = 'SHIPPED'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11-01'
  AND ordered_at = '2026-11-21T01:00:00Z'
  AND order_id = 22222222-2222-4222-8222-222222222222;
```

**Important note:** to update the second table accurately, you must know the **original primary key values** (`customer_id`, `order_month`, `ordered_at`, `order_id`). If the order timestamp changes during an update, Cassandra treats it as a different row; the application must handle deleting the old row and creating the new row.

### When a Partition Is Still Too Large

Splitting by month is not enough if a single customer creates millions of orders per month. You can split further by day, week, or a predefined **bucket**, but there is a trade-off: smaller buckets make queries spanning multiple buckets more complex. When listing across multiple months, the application queries multiple partitions and then merges/sorts the results. Use the driver's **paging state** to paginate within a query; avoid simulating `OFFSET` by scanning and skipping many rows.

## 4. Many-to-Many (N:M) Relationship: Students and Courses

**Problem:** a student enrolls in many courses and a course has many students. Two independent questions:

1. Which courses is student `S` currently taking?
2. Which students are enrolled in course `C`?

In an RDBMS, an associative table `enrollments(student_id, course_id)` and `JOIN` can serve both directions. In Cassandra, the direct approach is **two tables representing the same association, each keyed for one read direction**:

```sql
CREATE TABLE enrollments_by_student (
    student_id uuid,
    course_id uuid,
    enrolled_at timestamp,
    enrollment_status text,
    PRIMARY KEY ((student_id), course_id)
);

CREATE TABLE enrollments_by_course (
    course_id uuid,
    student_id uuid,
    enrolled_at timestamp,
    enrollment_status text,
    PRIMARY KEY ((course_id), student_id)
);
```

When a student enrolls in a course, write **the same relationship edge** to both tables:

```sql
INSERT INTO enrollments_by_student
    (student_id, course_id, enrolled_at, enrollment_status)
VALUES (
    44444444-4444-4444-8444-444444444444,
    33333333-3333-4333-8333-333333333333,
    '2026-11-21T02:00:00Z', 'ACTIVE'
);

INSERT INTO enrollments_by_course
    (course_id, student_id, enrolled_at, enrollment_status)
VALUES (
    33333333-3333-4333-8333-333333333333,
    44444444-4444-4444-8444-444444444444,
    '2026-11-21T02:00:00Z', 'ACTIVE'
);

-- Courses of a student.
SELECT course_id, enrolled_at, enrollment_status
FROM enrollments_by_student
WHERE student_id = 44444444-4444-4444-8444-444444444444;

-- Students of a course.
SELECT student_id, enrolled_at, enrollment_status
FROM enrollments_by_course
WHERE course_id = 33333333-3333-4333-8333-333333333333;
```

Reading in one direction only requires querying the table for that direction. Cassandra does not check whether the corresponding student or course exists in other entity tables; the application must enforce that when business rules require it.

When withdrawing a student from a course, you must update or delete **both relationship records**. If using a `CANCELLED` status instead of deleting, both tables must receive the same status. Keep `enrolled_at` and key-linked fields stable so re-writing with the same primary key is **idempotent** (repeating the operation does not create duplicate links).

**Scale limit to anticipate:** a course with millions of students can create a very large partition in `enrollments_by_course`. If this risk exists, you can design `PRIMARY KEY ((course_id, bucket), student_id)` and define how the bucket is computed. In that case, the application needs to know the bucket to query or scan the relevant buckets; there is no single key structure that is optimal for all scales and all query patterns.

## 5. Choosing a Representation Pattern by Read Path

| Relationship | Question to Answer | Typical Data Layout | What to Control |
| --- | --- | --- | --- |
| 1:1 | Fetch profile and preferences by `user_id` | One combined row or two tables sharing `user_id` as partition key | No foreign keys; read two tables if split |
| 1:N | List children by parent; find one child record by ID | `orders_by_customer_month` and `orders_by_id` | Partition size, updating two copies, querying across multiple buckets |
| N:M | List linked entities in both directions | `enrollments_by_student` and `enrollments_by_course` | Bidirectional writes/deletes, large partitions when cardinality is high |

One way to validate a design is to write the **actual CQL queries** before implementation. If a frequent query lacks the full partition key, must scan multiple partitions, or relies on `ALLOW FILTERING`, revisit the keys and consider creating a dedicated table for that query. Do not automatically use secondary indexes or materialized views as a general substitute for query-driven table design; each mechanism has its own performance and operational limitations.

## 6. Synchronizing Duplicated Data and Consistency Levels

Denormalization trades read-time `JOIN` cost for the work of **writing and maintaining multiple representations**. Suppose creating an order succeeds in `orders_by_id` but fails when writing to `orders_by_customer_month`: looking up by ID finds the order, while the customer's order list page does not show it yet. This is an **application-level** synchronization failure, even though each write received acknowledgment at the configured Cassandra consistency level.

A common workflow:

1. Identify the **source of truth** and the tables serving each read path; lock in the primary keys of all copies when the entity is created.
2. When a business event occurs, update the related tables using prepared statements (*prepared statement*). Keep the same ID, timestamp, and bucket on retries.
3. Accept that some read paths may temporarily diverge during errors/timeouts; monitor failed writes, perform controlled retries, and have a **reconciliation/data-repair** mechanism.
4. When deleting or changing an association, update all read-direction tables. When deleting, watch out for tombstones and heavy scan/delete loads.

Sketch example in a Java application layer, after preparing the two `INSERT` statements from section 3:

```java
// orderId, customerId, orderedAt, orderMonth, amount, status
// are fixed values for the same order.
session.execute(insertOrderById.bind(
    orderId, customerId, orderedAt, orderMonth, amount, status));

session.execute(insertOrderByCustomerMonth.bind(
    customerId, orderMonth, orderedAt, orderId, amount, status));

// If a write fails or times out: record it and retry/reconcile.
// Reuse the exact original keys to avoid creating logically duplicate rows.
```

In this example, `insertOrderById` and `insertOrderByCustomerMonth` are prepared `PreparedStatement` objects, and `session` is the Java Driver's `CqlSession`. The snippet illustrates **the two required writes**, not a complete error-handling pipeline; in a production system, you need to define retry policies, conflict handling, and tracking for each write outcome.

**Consistency level:** depending on the replication factor and topology, the application can use `LOCAL_QUORUM` for reads and writes to strengthen guarantees of seeing acknowledged data within the same datacenter. However, choosing `LOCAL_QUORUM` **does not create multi-table transactions** or foreign keys. A `LOGGED BATCH` provides batch write semantics and helps ensure all mutations are eventually applied, but it does not provide isolation or rollback like relational transactions; batches spanning multiple partitions also add overhead. Do not default to `BATCH` for every bidirectional write without evaluating correctness and actual load.

## 7. Common Pitfalls

| Common Mistake | Consequence | How to Handle |
| --- | --- | --- |
| Storing only `orders_by_id`, then trying to find all orders by `customer_id` | No efficient lookup path by partition key | Add a customer-list table with an appropriate bucket |
| Using `customer_id` alone as the partition key for millions of orders | Huge partition, potential hotspot | Split by month/day/bucket based on actual volume |
| Storing only `enrollments_by_student` when listing by course is needed | Cannot read efficiently by `course_id` | Add `enrollments_by_course` |
| Treating two tables sharing the same ID like a foreign-key relationship | Orphaned or out-of-sync data on failed writes/deletes | Enforce business checks, retries, and application-level reconciliation |
| Updating duplicated data in only one table | Different screens display inconsistent results | Inventory all copies affected by the event |
| Changing `ordered_at` or bucket expecting an in-place `UPDATE` | Old row may remain while a new row is created | Handle key changes as a controlled move or delete–insert operation |

## 8. Self-Check Practice Exercise

Design an **articles and tags** system with two requirements: (a) read the 10 most recent articles carrying a given tag; (b) read all tags attached to an article. Try answering before reading the hints:

1. What type of relationship is `article`–`tag`?
2. Which tables are needed to query efficiently in both directions?
3. What should the partition key and clustering columns be to fetch the latest articles by tag?
4. When removing a tag from an article, what must the application do?

**Suggested answers:** (1) N:M; (2) at least `tags_by_article` and `articles_by_tag` for the two read paths; (3) `articles_by_tag` can use partition key `(tag_id, time_bucket)` and clustering `(published_at DESC, article_id)`; (4) delete or update the association in both tables and reconcile if an error occurs. For an extremely popular tag, choose the bucket granularity according to the article creation rate and accept that the application must read multiple buckets when browsing across multiple time ranges.

## Conclusion

In Cassandra, **1:1** is typically represented as a single row or two tables sharing an ID; **1:N** partitions by the parent entity and uses clustering to list child entities; **N:M** usually requires separate tables for each lookup direction. Every choice must start from the queries, partition sizes, and consistency requirements. Duplicated data is a tool for efficient reads in a distributed system, while placing clear synchronization responsibilities on the application.
