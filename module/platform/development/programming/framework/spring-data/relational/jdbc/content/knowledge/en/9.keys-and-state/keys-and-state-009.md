# Composite Key Limitations and Version Compatibility Strategies

In a relational database, a row can be identified by a single primary key column or by a combination of multiple columns. A primary key composed of multiple components is called a **composite primary key**. This key style commonly appears when a record's identity is determined by multiple business factors, such as a tenant ID together with a product code, or an order ID together with a line number.

When using **Spring Data Relational JDBC**, distinguish database capabilities from the mapping capabilities of the Spring Data JDBC version in use. A database may support composite keys completely, yet the repository and object mapping mechanisms of a specific framework version may have their own limitations. Do not assume that JPA annotations like `@EmbeddedId` or `@IdClass` will automatically work in Spring Data JDBC.

This lesson presents how to understand composite keys, what to verify in Spring Data JDBC, compatibility strategies when upgrading or supporting multiple versions, and how to choose between a composite key and a surrogate key.

## 1. What is a composite primary key?

A composite primary key is a key formed from **two or more columns**, where the combination of values must be unique and each component participates in identifying a row.

Example `order_line` table:

~~~sql
CREATE TABLE order_line (
    order_id BIGINT NOT NULL,
    line_number INTEGER NOT NULL,
    product_code VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL,
    PRIMARY KEY (order_id, line_number)
);
~~~

In this table:

- `order_id` identifies the order.
- `line_number` identifies the line position within that order.
- Only the combination `(order_id, line_number)` uniquely identifies an order line.

Two rows can share `line_number = 1` if they belong to two different orders. Two rows can share `order_id` if they are two different lines. Neither column alone suffices as the primary key.

~~~text
order_id | line_number | product_code
---------+-------------+-------------
1001     | 1           | BOOK-A
1001     | 2           | PEN-B
1002     | 1           | BOOK-A

Key of first row  = (1001, 1)
Key of second row = (1001, 2)
Key of third row  = (1002, 1)
~~~

### 1.1. A composite primary key differs from a single column holding a concatenated string

You could construct a string `"1001-1"` from two values, yet that does not automatically make it a composite key. Such a string column brings problems:

- Encoding/decoding rules are needed to avoid boundary ambiguity between components.
- The database cannot enforce separate data types and constraints on each part.
- Sorting, filtering, and joining on individual components become cumbersome.
- Changing formatting rules can affect both data and APIs.

A composite key at the relational schema level keeps each column separate and declares uniqueness across the full combination.

### 1.2. Three commonly confused concepts

| Concept | Meaning | Example |
| --- | --- | --- |
| Composite primary key | Multiple columns together form the primary key | `PRIMARY KEY (tenant_id, product_code)` |
| Composite unique constraint | Multiple columns must be unique together, though not necessarily the primary key | `UNIQUE (tenant_id, email)` |
| Surrogate key | A technical key generated to identify a row | `id BIGINT GENERATED ... PRIMARY KEY` |

A table has only one primary key constraint, though that primary key can contain multiple columns. A table can also have multiple unique constraints to protect other business identities.

## 2. Why do businesses choose composite keys?

Composite keys often reflect the natural identity of data.

### 2.1. Scope-dependent identity

A product code may only be unique within one tenant:

~~~sql
CREATE TABLE tenant_product (
    tenant_id BIGINT NOT NULL,
    product_code VARCHAR(80) NOT NULL,
    name VARCHAR(200) NOT NULL,
    PRIMARY KEY (tenant_id, product_code)
);
~~~

In this case, `product_code` is not system-wide unique. Identity must include both `tenant_id` and `product_code`.

### 2.2. Child data numbered within parent scope

An order line can be identified by `(order_id, line_number)`. The line number only has meaning within a single order. This child data typically shares a lifecycle tied to the order.

### 2.3. Join table between two entities

A join table between students and courses can use the combination:

~~~sql
CREATE TABLE enrollment (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    enrolled_at TIMESTAMP NOT NULL,
    PRIMARY KEY (student_id, course_id)
);
~~~

The combination of two foreign keys prevents a student from enrolling in the same course twice. If the table needs to store multiple enrollments per term, add an identifying component such as `term_id` or `attempt_number`; key design must reflect actual business rules.

### 2.4. Advantages and costs

**Advantages**

- The key carries direct business meaning.
- Can avoid an extra technical ID column if the natural combination is already stable and unique.
- Uniqueness is enforced by the database directly on the business components.
- Child data can clearly express its identity scope.

**Costs**

- Referencing foreign keys must carry all components.
- Joins, updates, deletes, and queries must supply every key component.
- Indexes and foreign keys can be wider and consume more storage.
- When a key component changes, updating references is complex.
- ORM/JDBC mapping frameworks may have specific limitations for multi-component ID types.

Thus, a "natural key" is not always the "best key to use as primary key".

## 3. Database capabilities and Spring Data JDBC capabilities are two different things

Databases such as PostgreSQL, MySQL, or SQL Server can declare a primary key spanning multiple columns. Yet an application needs more than a valid schema; the framework must also know how to:

1. Read each key component from a row.
2. Construct a Java object representing the complete key.
3. Detect whether an object is new or existing.
4. Generate SQL statements filtering on all key components.
5. Bind parameters with the right data types.
6. Handle the ID on save and on reload.
7. Propagate all key components across relationships between aggregates or child entities if mapping requires it.

A database accepting:

~~~sql
PRIMARY KEY (tenant_id, product_code)
~~~

does not mean a repository can automatically handle any Java class containing those two fields. **Relational schema capability does not prove framework object-mapping capability.**

### 3.1. Do not copy JPA patterns verbatim into Spring Data JDBC

In JPA, developers commonly encounter:

- `@EmbeddedId` to declare an embedded ID object.
- `@IdClass` to describe a composite key class.
- `@Embeddable` to declare an embedded key/value type.

Spring Data JDBC uses Spring Data Relational mapping. `jakarta.persistence.EmbeddedId` and `jakarta.persistence.IdClass` are not part of Spring Data JDBC's mapping contract. Adding JPA annotations to a class does not magically enable composite ID support in JDBC.

Likewise, Spring Data Relational's `@Embedded` is an annotation for objects mapped onto columns within a row. It should not be treated as an alias carrying the full semantics of JPA's `@EmbeddedId`.

Always check package imports:

~~~java
// Spring Data JDBC:
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

// Do not treat the following annotations as Spring Data JDBC's composite key mechanism:
// import jakarta.persistence.EmbeddedId;
// import jakarta.persistence.IdClass;
~~~

## 4. Checking composite ID support by version

Composite key mapping capability is part of the framework contract, not merely a DDL detail. Spring Data JDBC and Spring Data Relational have evolved across multiple releases; do not assume an older project and a newer project share the same capabilities.

When evaluating composite IDs, verify at least:

- The actual resolved version of `spring-data-relational`.
- The corresponding version of `spring-data-jdbc`.
- The compatible release train and Spring Framework version.
- The Spring Boot/BOM version managing dependencies.
- Supported composite ID types in that version and component-mapping rules.
- Dialect/database compatibility and the repository operations you need.

**Do not guess Spring Data JDBC capabilities directly from the Spring Boot version number.** Spring Boot manages a set of dependencies via a BOM; what matters is the actual artifact version after Gradle resolves dependencies.

### 4.1. Determining actual dependency versions with Gradle

On Windows:

~~~powershell
.\gradlew.bat dependencyInsight --dependency spring-data-relational --configuration runtimeClasspath
~~~

And check the JDBC module:

~~~powershell
.\gradlew.bat dependencyInsight --dependency spring-data-jdbc --configuration runtimeClasspath
~~~

On Linux/macOS:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-data-relational \
  --configuration runtimeClasspath
~~~

The `dependencyInsight` command identifies the selected version and the dependency path leading to that version. This is useful when dependencies are managed through the Spring Boot plugin, a platform/BOM, or pulled in by another library.

If the project uses a configuration other than `runtimeClasspath` (e.g., a non-application module or custom configuration), select the appropriate configuration. Do not inspect a version declared in a single file in isolation and assume it is the version actually running.

### 4.2. Reading documentation for the exact release

When a composite ID is needed:

1. Obtain the resolved `spring-data-relational`/`spring-data-jdbc` version.
2. Open the reference documentation and release notes for that exact version line.
3. Locate the identifier/composite identifier mapping section.
4. Check supported ID types, annotation placement, and how components are mapped.
5. Check limitations around generated IDs, child references, repository CRUD, and custom queries.
6. Write integration tests against the actual database/dialect before broad adoption.

Do not use documentation from the latest branch to claim an application running an older version has the same behavior. Newer documentation may describe features that do not exist in the release your application uses.

### 4.3. Decision matrix based on version capabilities

Instead of relying on guesses about release milestones, classify according to verified capabilities:

| Scenario | Strategy |
| --- | --- |
| Current version does not support composite IDs the way the model requires | Use a surrogate key as primary key; protect business identity with a composite unique constraint. |
| Version supports composite IDs, yet only covers certain mapping styles | Use only after every required operation has been verified; if gaps remain, use a surrogate key. |
| Version fully supports the required ID types and relationships | Can use composite IDs directly if business benefits outweigh reference overhead. |
| Application must run across multiple releases | Choose the intersecting design supported by all releases, usually surrogate key + unique constraint. |
| Framework upgrade is planned | Separate the upgrade from schema/ID changes if possible; test each change independently to isolate risk. |

This matrix is intentionally grounded in **verified artifact capabilities**, rather than attributing a feature to all versions without checking release notes. Exact support milestones must come from documentation for the specific version the application intends to use.

## 5. Broad compatibility strategy: surrogate key and unique constraint

When supporting multiple Spring Data JDBC versions or wanting simple repositories, the most broadly compatible approach is usually:

- Use a simple technical key as the primary key.
- Keep business components in separate columns.
- Declare a unique constraint on the business combination.

Example tenant product table:

~~~sql
CREATE TABLE tenant_product (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    product_code VARCHAR(80) NOT NULL,
    name VARCHAR(200) NOT NULL,
    CONSTRAINT uk_tenant_product_code
        UNIQUE (tenant_id, product_code)
);
~~~

Entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("tenant_product")
public class TenantProduct {

    @Id
    private Long id;

    private Long tenantId;
    private String productCode;
    private String name;

    public TenantProduct(
            Long id,
            Long tenantId,
            String productCode,
            String name
    ) {
        this.id = id;
        this.tenantId = tenantId;
        this.productCode = productCode;
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public Long getTenantId() {
        return tenantId;
    }

    public String getProductCode() {
        return productCode;
    }

    public String getName() {
        return name;
    }
}
~~~

Repository with a simple key:

~~~java
public interface TenantProductRepository
        extends CrudRepository<TenantProduct, Long> {

    Optional<TenantProduct> findByTenantIdAndProductCode(
            Long tenantId,
            String productCode
    );
}
~~~

Outcome:

- Spring Data JDBC uses `id` as the entity's identifier.
- Business logic still looks up records by `tenantId + productCode`.
- The database guarantees that combination cannot duplicate even under concurrent requests.
- Foreign keys from other tables only need to reference a single `id` column.
- When a product code changes under business rules, the technical primary key does not need to change.

### 5.1. Unique constraint is the final line of defense

Checking existence in Java before inserting is not enough to guarantee uniqueness:

~~~java
if (!repository.existsByTenantIdAndProductCode(tenantId, code)) {
    repository.save(product);
}
~~~

Two requests can both observe "does not exist yet" before either inserts. Then both try to create a duplicate record.

A database unique constraint resolves that race:

~~~text
Request A: SELECT -> absent
Request B: SELECT -> absent
Request A: INSERT -> succeeds
Request B: INSERT -> unique constraint violation
~~~

The application can still pre-check to return a friendly message, yet it must handle constraint errors when saving. Do not substitute a pre-check query for a unique constraint.

### 5.2. When is a surrogate key a good choice?

Surrogate keys are especially helpful when:

- Business key components can change.
- The key has multiple columns and is referenced by many tables.
- The system needs compatibility across multiple persistence framework versions.
- Aggregates have many relationships or CRUD operations need a simple ID.
- APIs and events need a short, stable identifier.

The downside is an extra column and a unique constraint. However, that cost is usually smaller than propagating composite keys throughout the entire system.

## 6. When should you use a composite ID directly?

A composite ID can make sense if the key combination is:

- Stable throughout the data's lifecycle.
- Free of components that can be arbitrarily edited.
- Naturally meaningful in the domain.
- Protected by a primary key in the database.
- Fully supported by the framework version in use.
- Not an excessive burden on referencing relationships and APIs.

Example `EnrollmentId`:

~~~java
public record EnrollmentId(Long studentId, Long courseId) {
    public EnrollmentId {
        if (studentId == null || studentId <= 0) {
            throw new IllegalArgumentException("Invalid studentId");
        }
        if (courseId == null || courseId <= 0) {
            throw new IllegalArgumentException("Invalid courseId");
        }
    }
}
~~~

This record expresses the key's value clearly and provides equality across both components. However, declaring a record **does not automatically make Spring Data JDBC support composite ID mapping**. You must follow the exact ID declaration convention required by your Spring Data Relational version.

If your release supports composite IDs with an ID value type, the conceptual structure may look like:

~~~text
Enrollment
  id: EnrollmentId
       studentId
       courseId
  enrolledAt

Database:
  enrollment.student_id
  enrollment.course_id
  PRIMARY KEY (student_id, course_id)
~~~

This is a conceptual model. Before using it in real code, confirm the annotations/flattening conventions supported by your release; do not apply JPA's `@EmbeddedId` or assume every field inside a record will automatically flatten into key columns.

### 6.1. Composite keys should be immutable

If `studentId` or `courseId` changes, the enrollment's identity changes too. Changing keys may require:

- Updating all referencing foreign keys.
- Handling cascades or update ordering.
- Avoiding windows of inconsistent data.
- Reconciling already published events, cache keys, and URLs/APIs.

Therefore, composite ID components should be stable values. If components change frequently, consider a surrogate key.

### 6.2. Do not use nullable values in keys

Database primary keys do not accept null under standard semantics. Every key component must have a valid value before saving. The ID value type should validate this in its constructor/factory; the schema must also declare the key columns as `NOT NULL`.

### 6.3. Equality and hash code

Composite IDs are usually value objects. Comparing two IDs across all components makes sense:

~~~java
EnrollmentId a = new EnrollmentId(10L, 20L);
EnrollmentId b = new EnrollmentId(10L, 20L);

System.out.println(a.equals(b)); // true
~~~

Java records automatically generate `equals()` and `hashCode()` from their components, fitting immutable ID types like this. If using a regular class, implement both methods consistently across all key components.

## 7. Composite keys in relationships and foreign keys

A major drawback of composite keys lies not in the base table, but in **every table that references it**.

If `tenant_product` uses primary key `(tenant_id, product_code)`, an inventory table may need:

~~~sql
CREATE TABLE inventory (
    tenant_id BIGINT NOT NULL,
    product_code VARCHAR(80) NOT NULL,
    warehouse_code VARCHAR(40) NOT NULL,
    available_quantity INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, product_code, warehouse_code),
    FOREIGN KEY (tenant_id, product_code)
        REFERENCES tenant_product (tenant_id, product_code)
);
~~~

Every join requires both columns:

~~~sql
SELECT i.warehouse_code, i.available_quantity
FROM inventory i
JOIN tenant_product p
  ON p.tenant_id = i.tenant_id
 AND p.product_code = i.product_code
WHERE p.tenant_id = ?
  AND p.product_code = ?;
~~~

With a surrogate key, relationships can be simpler:

~~~sql
CREATE TABLE tenant_product (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    product_code VARCHAR(80) NOT NULL,
    CONSTRAINT uk_tenant_product UNIQUE (tenant_id, product_code)
);

CREATE TABLE inventory (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_product_id BIGINT NOT NULL
        REFERENCES tenant_product(id),
    warehouse_code VARCHAR(40) NOT NULL,
    available_quantity INTEGER NOT NULL,
    CONSTRAINT uk_inventory_product_warehouse
        UNIQUE (tenant_product_id, warehouse_code)
);
~~~

Foreign keys are shorter, referencing indexes are usually simpler, and business code changes do not alter referenced keys.

### 7.1. Relation to aggregates in Spring Data JDBC

Spring Data JDBC persists an aggregate through its root. Child collections are typically linked to the root via foreign keys and corresponding mapping metadata. If the root has a composite ID, verify that your release supports propagating all key components to child tables and generating SQL for collections.

Do not test only single-root reads. Test:

- Inserting a new root.
- Loading the root by ID.
- Updating the root.
- Inserting/updating/deleting child collections.
- Deleting the aggregate and handling children.
- Referencing the aggregate from another table or aggregate.

A composite ID may work for simple operations yet lack support on another mapping path. Integration tests must cover the exact operations your application actually uses.

## 8. Repositories and queries with composite keys

With a surrogate key, the CRUD repository is straightforward:

~~~java
interface TenantProductRepository
        extends CrudRepository<TenantProduct, Long> {
}
~~~

Look up by business identity:

~~~java
Optional<TenantProduct> findByTenantIdAndProductCode(
        Long tenantId,
        String productCode
);
~~~

With a composite ID, if the version supports it, the repository can use the ID value object type in its generic parameter:

~~~java
// Illustrates the API shape when composite IDs are supported by the release.
interface EnrollmentRepository
        extends CrudRepository<Enrollment, EnrollmentId> {
}
~~~

This declaration is only appropriate when composite identifier mapping has been confirmed in the version in use. Java generics cannot supply persistence capabilities that the framework lacks.

### 8.1. Manual queries

If custom SQL is needed, always pass all components:

~~~java
@Query("""
       SELECT student_id, course_id, enrolled_at
       FROM enrollment
       WHERE student_id = :studentId
         AND course_id = :courseId
       """)
Optional<Enrollment> findEnrollment(
        Long studentId,
        Long courseId
);
~~~

Placeholder naming and binding capabilities depend on the query API used. With `JdbcClient`, you can write explicitly:

~~~java
return jdbcClient.sql("""
        SELECT student_id, course_id, enrolled_at
        FROM enrollment
        WHERE student_id = :studentId
          AND course_id = :courseId
        """)
    .param("studentId", studentId)
    .param("courseId", courseId)
    .query(Enrollment.class)
    .optional();
~~~

Manual queries let you declare each column explicitly, yet they do not automatically handle every aggregate save/delete operation. Clearly decide which parts are managed by the repository and which by custom SQL to avoid two conflicting update paths.

### 8.2. Do not concatenate keys via SQL strings

Avoid:

~~~java
String sql = "SELECT * FROM enrollment WHERE student_id = "
        + studentId + " AND course_id = " + courseId;
~~~

Use bind parameters to preserve data types and prevent SQL injection:

~~~java
jdbcClient.sql("""
        SELECT *
        FROM enrollment
        WHERE student_id = :studentId
          AND course_id = :courseId
        """)
    .param("studentId", studentId)
    .param("courseId", courseId)
    .query(Enrollment.class);
~~~

Do not pass a single string `studentId + "-" + courseId` as one parameter if the database has two separate key columns.

## 9. Migration strategy when switching from composite key to surrogate key

A running system with a composite primary key may want to switch to a surrogate key to simplify persistence mapping. This is a significant schema change because multiple tables may be referencing the old key components.

Suppose the original table:

~~~sql
CREATE TABLE tenant_product (
    tenant_id BIGINT NOT NULL,
    product_code VARCHAR(80) NOT NULL,
    name VARCHAR(200) NOT NULL,
    PRIMARY KEY (tenant_id, product_code)
);
~~~

Target:

~~~sql
CREATE TABLE tenant_product (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    product_code VARCHAR(80) NOT NULL,
    name VARCHAR(200) NOT NULL,
    UNIQUE (tenant_id, product_code)
);
~~~

A phased transition strategy:

**Phase 1 — Add the ID column**

- Add the `id` column with an appropriate value generation mechanism.
- Backfill IDs for all existing rows.
- Create a unique index/constraint on `id`.
- Keep the composite primary key while older application versions still depend on it.

**Phase 2 — Update referencing tables**

- Add the `tenant_product_id` column to each child/consumer table that references it.
- Backfill by joining on the old key.
- Create new foreign keys and indexes.
- Verify no referencing records are missing or mismatched.

**Phase 3 — Deploy compatible application versions**

- Gradually switch application versions to read/write the new ID according to the chosen migration strategy.
- If old and new versions must run concurrently, clearly define which version writes which columns and how synchronization works.
- Do not drop the old key while old instances or jobs still rely on it.

**Phase 4 — Switch the primary key**

- Only after all references and applications use the new ID, switch the primary key to `id`.
- Keep the unique constraint on `(tenant_id, product_code)` to protect business identity.
- Drop old foreign keys/indexes after verifying no consumers remain.

DDL ordering, online constraint-change capabilities, and backfill syntax depend on the database. For large tables, evaluate locks, index build time, replication lag, and rollout strategy. Do not apply a one-size-fits-all script across every database system.

### 9.1. Reverse migration: from surrogate key to composite ID

Switching from a simple ID to a composite ID usually costs more in reference changes than it saves:

- Every foreign key must expand into multiple columns.
- APIs, caches, logs, events, and URLs may have to change.
- Repository generic IDs and method signatures must change.
- External consumers may depend on the old ID.

If the goal is solely to protect business uniqueness, **keeping the surrogate primary key and adding a composite unique constraint** is usually enough. Only change the primary key when there is a clear architectural reason.

## 10. Managing dependency versions to avoid compatibility drift

In Gradle, Spring Boot usually manages Spring Data versions through dependency management/BOM. Manually declaring a different version for `spring-data-jdbc` or `spring-data-relational` alone can create an untested combination.

### 10.1. Prefer a single version management source

Example using Spring Boot plugin/BOM:

~~~groovy
plugins {
    id 'org.springframework.boot' version '<boot-version>'
    id 'io.spring.dependency-management' version '<plugin-version>'
    id 'java'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

Placeholders must be replaced with versions chosen from your project's compatibility matrix. When using starters, let the BOM manage Spring Data artifacts unless performing an intentional, tested upgrade.

If managing Spring Data independently of Spring Boot, use the corresponding release train/BOM and verify compatibility with Spring Framework and the Java baseline. Do not upgrade a single submodule while leaving other Spring Data modules on an older release train.

### 10.2. Avoid overriding a single artifact to "unlock" a feature

Risky example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    implementation 'org.springframework.data:spring-data-relational:<new-version>'
}
~~~

If the overridden version is incompatible with the Spring Data JDBC managed by the starter, the application may hit binary/API errors or unsupported mapping behavior. To adopt a new feature:

1. Identify the release train that includes the feature.
2. Choose a compatible Spring Boot/Spring Framework version for that release train.
3. Upgrade the BOM/platform together.
4. Run compilation, integration tests, and inspect SQL.
5. Only override an individual version if official documentation permits it and that combination has been tested.

### 10.3. Compatibility is more than compiling successfully

A class can compile even if composite ID mapping is not supported by the framework in the intended way. Runtime is when SQL is generated, IDs are bound, and rows are materialized. Test at least the critical persistence operations on a real database or Testcontainers with the right dialect.

## 11. Testing composite IDs and version compatibility

Tests should verify schema, mapping, and CRUD behavior together.

### 11.1. Verifying uniqueness in the database

~~~sql
INSERT INTO enrollment(student_id, course_id, enrolled_at)
VALUES (10, 20, CURRENT_TIMESTAMP);

-- The same combination must be rejected.
INSERT INTO enrollment(student_id, course_id, enrolled_at)
VALUES (10, 20, CURRENT_TIMESTAMP);
~~~

The second statement must violate the primary key/unique constraint. Tests should verify the application handles the exception properly.

### 11.2. Verifying the repository lifecycle

| Test case | What to verify |
| --- | --- |
| Insert new entity | Every key component is written accurately; none omitted or bound in the wrong order/type. |
| Load by ID | Can reconstruct the exact ID object from all key columns. |
| Save/update | Update conditions use all key components. |
| Delete | Deletes only the row matching all ID components. |
| Child collection | Root key propagates properly to child tables. |
| Foreign key | References from other tables are properly enforced. |
| Custom query | Parameter mapping and projections work with actual data types. |
| Concurrency | Unique constraints/optimistic locking handle contention as expected. |
| Migration | Old data and old references remain valid after rollout. |

### 11.3. Inspecting generated SQL

Enable SQL logging in an appropriate test environment or use a datasource proxy to observe:

- Column count in `INSERT`.
- `WHERE` conditions of `UPDATE` and `DELETE`.
- Each bound parameter and its data type.
- SQL operating on child collections.
- Whether appropriate indexes are used via execution plans.

Do not merely assert that the repository returns the right object. A test might accidentally verify data inserted via a different SQL path; make sure the Spring Data JDBC mapping path itself is genuinely exercised.

### 11.4. Running a version matrix

~~~text
                 Integration test suite
                          |
             +------------+------------+
             |            |            |
          Version A    Version B    Version C
             |            |            |
             v            v            v
        insert/load   insert/load   insert/load
        update/delete update/delete update/delete
        child refs    child refs    child refs
             |            |            |
             +------------+------------+
                          |
                 Compare expected behavior
~~~

Each version must use the dependency set matching its release train. Do not attempt to run a single classpath containing multiple Spring Data versions simultaneously; separate the build/test matrix into distinct modules or jobs.

## 12. Choosing keys for each kind of data

| Data type | Usually suitable key | Reason |
| --- | --- | --- |
| Users, orders, products with long lifecycles | Simple surrogate ID, plus a unique business key if needed | ID stays stable when business attributes change. |
| Join table of two immutable IDs with no independent lifecycle | Composite key of two foreign keys or surrogate ID + unique constraint | Choose based on framework support and reference needs. |
| Order lines numbered within order scope | `(order_id, line_number)` or surrogate child ID | Line number is meaningful in the aggregate; consider reordering/deletion/reinsertion. |
| Product codes unique only per tenant | `UNIQUE(tenant_id, product_code)`; simple or composite primary key depending on architecture | Uniqueness scope must be enforced by the database. |
| Historical data with multiple versions of the same object | Separate version ID or composite key containing version/effective time | Identity must distinguish each historical record. |
| Events with a source and sequence number within the source | `(source_id, sequence_number)` can fit well | Stable combination reflecting unique ordering within the source. |

Do not pick a composite ID merely because two columns currently look unique. Ask whether they will remain unique, non-null, and unchanged throughout the entire lifecycle.

## 13. Common mistakes

| Mistake | Impact | Resolution |
| --- | --- | --- |
| Using `@EmbeddedId`/`@IdClass` out of JPA habit | Spring Data JDBC does not understand JPA contract annotations | Use Spring Data Relational annotations matching your release or choose a surrogate ID. |
| Assuming database support means repository support | Runtime mapping or CRUD may fail | Check reference docs, release notes, and integration tests. |
| Declaring a composite ID as a record and assuming it works automatically | A record only creates a Java type, not mapping features | Verify how the framework maps ID value types. |
| Passing only part of the key in queries | Reads wrong rows or updates/deletes wrong rows | Always bind all components. |
| Concatenating strings to simulate a key | Loses data types and per-column rules | Keep components as separate columns. |
| Missing unique constraint | Two concurrent requests can create duplicate records | Enforce uniqueness at the database level. |
| Key components can change frequently | Cascading updates to foreign keys and caches | Use a stable surrogate ID. |
| Overriding a single Spring Data artifact version | Can introduce incompatible dependencies | Upgrade together via BOM/release train. |
| Testing with H2 and assuming it holds for production DB | Dialect, identity, and constraint behavior may differ | Test with the actual database/dialect or Testcontainers. |
| Testing only findById | Misses update/delete/child mapping bugs | Test the entire aggregate lifecycle. |

## 14. Decision workflow

When designing a table or aggregate that needs a composite key, follow this sequence:

1. **Define business identity.** Explicitly list which components combine to identify a record.
2. **Check stability.** Can any component change, be null, need normalization, or be reused?
3. **Design constraints.** Use a primary key or unique constraint so the database enforces the rule.
4. **Check the framework.** Verify the actual Spring Data JDBC version and required mapping capabilities.
5. **Evaluate relationships.** Count the tables, aggregates, and APIs that would have to carry all key components.
6. **Choose an approach.** Use a composite ID if fully supported and clearly beneficial; otherwise, use a surrogate key with a composite unique constraint.
7. **Test at runtime.** Verify insert, load, update, delete, child collections, foreign keys, and concurrency.
8. **Plan upgrades.** When versions change, re-check the mapping contract before removing older compatibility workarounds.

## Key takeaways

Composite keys are a valid choice at the relational database layer, yet using them directly in Spring Data JDBC depends on the mapping contract of your framework version. Do not treat JPA annotations as proof of support. Identify the resolved artifact versions, read documentation for the exact release, and thoroughly test all operations you need.

When broad compatibility is needed or you want simpler relationships, a **surrogate primary key combined with a unique constraint across business components** is usually a durable strategy: repositories have a simple ID, the database still protects natural identity, and referencing tables avoid carrying entire key combinations across the system.
