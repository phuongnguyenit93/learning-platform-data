# Choosing Soft Delete or Filter Mechanisms by Hibernate Version

## Objectives

After this lesson, you will be able to distinguish soft delete from data filtering mechanisms; choose `@SoftDelete`, `@SQLDelete` combined with a restriction, `@SQLRestriction`, or `@Filter` based on Hibernate version; understand changes from `javax.persistence` to `jakarta.persistence`; configure session-scoped filters; and test soft deletion, loading by ID, relationships, native queries, and data restoration.

Examples use Java 17+ and Spring Data JPA. Annotations such as `@SoftDelete`, `@SQLDelete`, `@SQLRestriction`, and `@Filter` are Hibernate-specific APIs, not part of Jakarta Persistence. Check the exact Hibernate version managed by Spring Boot before copying examples.

## 1. Soft Delete and Filters Solve Two Different Problems

Soft delete handles deleting an entity while keeping its row in the database. Instead of issuing a `DELETE` statement, the ORM updates a marker column, such as `deleted = true` or `deleted_at = CURRENT_TIMESTAMP`. Normal queries skip soft-deleted rows.

A filter adds a condition to queries to restrict the dataset to the current context—for example, retrieving only published documents, documents belonging to the current tenant, data within a date range, or records with a selected status. Filters can usually be enabled/disabled and parameterized per Hibernate Session.

Three mechanisms to distinguish:

| Mechanism | Role | Runtime parameters? | Replaces DELETE operation? |
| --- | --- | --- | --- |
| `@SoftDelete` | Maps soft-delete lifecycle on supported entities/collections | No filter parameter needed for deletion state | Yes; Hibernate turns delete operations into flag/timestamp updates |
| `@SQLDelete` + `@Where` or `@SQLRestriction` | Explicitly writes SQL to update the delete flag and declares a condition to hide rows | No; restriction is static | `@SQLDelete` does; restriction only filters reads |
| `@Filter` | Enables dynamic conditions per Session, commonly used for data scoping | Yes | No; filters do not automatically turn DELETE into soft delete |
| `@SQLRestriction` | Appends a static SQL condition to entity/collection queries | No | No; only alters generated SQL predicates |

Therefore, if the requirement is to call `EntityManager.remove()` while retaining the row in the database, choose a soft-delete mechanism. If the requirement is for the same entity to be queried by different tenants, statuses, or time ranges across Sessions, consider `@Filter`. Both can be combined when business rules require it, provided you understand which condition always applies and which takes effect only when a Session enables the filter.

## 2. Compatibility Matrix by Hibernate Version

| Hibernate Version | Recommended Mechanism | Important Notes |
| --- | --- | --- |
| 5.6 | `@SQLDelete` + `@Where`; `@Filter` for dynamic conditions | Hibernate 5.6 uses `javax.persistence`; neither `@SoftDelete` nor `@SQLRestriction` exists |
| 6.0–6.2 | `@SQLDelete` + `@Where`; `@Filter` | Hibernate 6 moves to `jakarta.persistence`; `@SoftDelete` is not yet available |
| 6.3 | `@SQLDelete` + `@SQLRestriction`; `@Filter` | `@Where` is deprecated starting in 6.3; use `@SQLRestriction` for static restrictions |
| 6.4–6.5 | Prefer `@SoftDelete` for supported entities/collections; `@Filter` for dynamic conditions | `@SoftDelete` was added in 6.4; 6.4/6.5 documentation describes boolean `ACTIVE` and `DELETED` strategies |
| 6.6 | `@SoftDelete`, `@SQLRestriction`, `@Filter` | `@FilterDef` adds options such as `applyToLoadByKey`; check incubating status and exact minor version |
| 7.x | `@SoftDelete`, `@SQLRestriction`, `@Filter` | Current Hibernate 7.4 docs also describe the `TIMESTAMP` strategy; do not assume it exists in every 7.x minor or in Hibernate 6.x |

Key version-transition notes:

- Hibernate 5.6 typically pairs with Spring Boot 2.x and imports `javax.persistence.*`.
- Hibernate 6.x and 7.x use Jakarta Persistence, so entities import `jakarta.persistence.*`.
- `@SoftDelete` was introduced in Hibernate 6.4. If a project uses Hibernate 6.3 or earlier, code using this annotation will not compile.
- `@Where` is deprecated from Hibernate 6.3; `@SQLRestriction` is the replacement API for static SQL restrictions.
- `@SoftDelete` is a Hibernate API. If you need to switch JPA providers, you must redesign or move the logic to the database or application layer.

Do not look solely at the Spring Boot version in `pom.xml` to decide APIs. Check the actual resolved dependencies—for example with `mvn dependency:tree` or `gradle dependencies`—because dependency management may select a different Hibernate minor version than the examples above.

## 3. The `@SoftDelete` Mechanism Since Hibernate 6.4

`@SoftDelete` is the preferred choice when the Hibernate version supports it and the mapping fits. Hibernate manages the deletion indicator column: when persisting an entity, the row is created as not deleted; when calling `remove()`, Hibernate updates the indicator column instead of physically deleting; normal entity queries automatically add a predicate to skip deleted rows.

Example using the `DELETED` strategy:

```java
package com.example.learning.document;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.SoftDelete;
import org.hibernate.annotations.SoftDeleteType;

@Entity
@Table(name = "documents")
@SoftDelete(strategy = SoftDeleteType.DELETED, columnName = "deleted")
public class Document {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String title;

    protected Document() {
    }

    public Document(String title) {
        this.title = title;
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
}
```

With the `DELETED` strategy, `true` means the row is deleted and `false` means the row is active. If `strategy` is omitted, `DELETED` is the default. The default column name is also `deleted`, though declaring `columnName` explicitly is good practice when schemas use different naming conventions.

### 3.1. ACTIVE and DELETED strategies

`SoftDeleteType` in Hibernate 6.4/6.5 has two boolean interpretations:

| Strategy | Database Value | Meaning | Default Column Name |
| --- | --- | --- | --- |
| `DELETED` | `true` | Deleted | `deleted` |
| `DELETED` | `false` | Active | `deleted` |
| `ACTIVE` | `true` | Active | `active` |
| `ACTIVE` | `false` | Deleted | `active` |

Example if the existing schema already has an `active` column:

```java
@Entity
@Table(name = "documents")
@SoftDelete(strategy = SoftDeleteType.ACTIVE, columnName = "active")
public class Document {
    // Entity properties
}
```

Do not invert the column's meaning by writing a custom reversed converter. A converter only converts the boolean value to the storage type; Hibernate handles interpreting the strategy. Common converters include `NumericBooleanConverter`, `YesNoConverter`, and `TrueFalseConverter`. Configure a converter only if the column type or schema requires it.

### 3.2. Collections and entity inheritance

Hibernate supports `@SoftDelete` on entities and on certain collection tables:

- Place it on the root entity of an inheritance hierarchy to apply to entities in that hierarchy.
- Can be placed on `@ElementCollection` to soft-delete individual rows in the collection table.
- Can be placed on `@ManyToMany` to soft-delete rows in the join table.
- Do not place `@SoftDelete` directly on a `@OneToMany` association; Hibernate reports a mapping error. If the child entity needs soft delete, place `@SoftDelete` on the child entity itself.

Collection table example:

```java
@ElementCollection
@CollectionTable(name = "document_labels", joinColumns = @JoinColumn(name = "document_id"))
@Column(name = "label")
@SoftDelete(columnName = "deleted")
private Set<String> labels = new HashSet<>();
```

This is an example for `@ElementCollection`; it requires appropriate imports and field declarations inside an actual entity. For `@OneToMany`, explicitly decide whether deleting a parent should soft-delete children and test cascading and orphan removal. Do not infer that marking a parent deleted automatically marks every child entity.

### 3.3. Timestamp strategy in current Hibernate 7.x

Current Hibernate 7.4 documentation additionally describes the `TIMESTAMP` strategy, storing the deletion timestamp instead of only a boolean. Example:

```java
@Entity
@Table(name = "documents")
@SoftDelete(strategy = SoftDeleteType.TIMESTAMP, columnName = "deleted_at")
public class Document {
    // Entity properties
}
```

With this strategy, the column stores the deletion timestamp; do not configure a boolean `AttributeConverter` alongside `TIMESTAMP`. Hibernate 6.4/6.5 and 6.6 documentation describe the boolean strategies, so use `TIMESTAMP` only when the Javadocs/User Guide of your exact runtime version confirm support. Never take a 7.4 example and drop it directly into a 6.x project.

`TIMESTAMP` records when a row was deleted, but does not automatically record who performed it, why, or full change history. If full auditing is needed, add audit fields or use an auditing solution such as Hibernate Envers as required.

## 4. Using `@SQLDelete` in Hibernate 5.6 Through 6.2

Before Hibernate 6.4, a common approach was replacing the default SQL DELETE with an UPDATE and adding a restriction to hide deleted rows.

Example for an entity without `@Version`:

```java
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.Table;
import org.hibernate.annotations.SQLDelete;
import org.hibernate.annotations.Where;

@Entity
@Table(name = "documents")
@SQLDelete(sql = "UPDATE documents SET deleted = true WHERE id = ?")
@Where(clause = "deleted = false")
public class Document {
    @Id
    private Long id;

    private String title;

    protected Document() {
    }
}
```

This illustrates the mapping for Hibernate 5.6 using `javax.persistence`. For Hibernate 6.0–6.2, replace `javax.persistence.*` imports with `jakarta.persistence.*`; `@SQLDelete` and `@Where` remain Hibernate annotations.

The two annotations perform two separate tasks:

- `@SQLDelete` replaces the DELETE statement Hibernate emits when an entity is removed with an UPDATE setting `deleted = true`.
- `@Where` appends a static SQL condition so entity/collection queries skip `deleted = true` rows.

With only `@SQLDelete`, marked rows can still appear in queries. With only `@Where`, remove operations still delete physically. To achieve soft delete with this approach, both parts are required.

### 4.1. Entities with `@Version` require attention to parameter order

If an entity is versioned, the custom SQL must contain the exact number of `?` placeholders in the order Hibernate expects. With `@SQLDelete`, primary key columns precede the version column. Illustrative example:

```java
@SQLDelete(
    sql = "UPDATE documents SET deleted = true WHERE id = ? AND version = ?"
)
```

This is only a fragment for an entity with a single primary key and one version column. Entities with composite keys or multi-table mappings need SQL matching the exact column count and parameter order bound by Hibernate. Check the `@SQLDelete` Javadocs, SQL logs, and integration tests on your exact mapping; a wrong placeholder can break the statement or invalidate version checking.

## 5. Since Hibernate 6.3: Replacing `@Where` with `@SQLRestriction`

`@Where` was deprecated in Hibernate 6.3. For fixed restrictions, use `@SQLRestriction`:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.SQLDelete;
import org.hibernate.annotations.SQLRestriction;

@Entity
@Table(name = "documents")
@SQLDelete(sql = "UPDATE documents SET deleted = true WHERE id = ?")
@SQLRestriction("deleted = false")
public class Document {
    @Id
    private Long id;

    private String title;

    protected Document() {
    }
}
```

`@SQLRestriction` is a native SQL predicate appended to SQL generated by Hibernate for an entity or collection. It always applies and cannot be turned off at runtime; it does not support bind parameters. Therefore, it suits fixed conditions such as `deleted = false`, not a tenant ID or status that varies per request.

For join tables, Hibernate provides `@SQLJoinTableRestriction`. In older versions, the corresponding annotation was `@WhereJoinTable`, which was likewise deprecated in 6.3 in favor of `@SQLJoinTableRestriction`.

## 6. Using `@Filter` for Session-Scoped Dynamic Conditions

`@Filter` is intended for cases where the filter condition varies at runtime. A filter is defined with `@FilterDef`, attached to an entity or collection with `@Filter`, and enabled on the Hibernate `Session` before running queries.

Example filtering documents by status:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import org.hibernate.annotations.Filter;
import org.hibernate.annotations.FilterDef;
import org.hibernate.annotations.ParamDef;

@Entity
@FilterDef(
    name = "documentStatus",
    parameters = @ParamDef(name = "status", type = String.class)
)
@Filter(
    name = "documentStatus",
    condition = "status = :status"
)
public class Document {
    @Id
    private Long id;

    private String status;

    // Constructor and accessors
}
```

The condition inside `@Filter` is a SQL fragment, so use the database column name (`status` in this example), not the Java property name if the column was renamed via `@Column`.

Enabling the filter within a transaction:

```java
import jakarta.persistence.EntityManager;
import org.hibernate.Filter;
import org.hibernate.Session;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentSearchService {
    private final EntityManager entityManager;

    public DocumentSearchService(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Transactional(readOnly = true)
    public List<Document> findByStatus(String status) {
        Session session = entityManager.unwrap(Session.class);
        Filter filter = session.enableFilter("documentStatus");
        filter.setParameter("status", status);
        try {
            return entityManager.createQuery(
                "select d from Document d order by d.id", Document.class
            ).getResultList();
        } finally {
            session.disableFilter("documentStatus");
        }
    }
}
```

This example demonstrates enabling the filter in the same Session executing JPQL. `java.util.List` must be imported. If a Session is shared across multiple operations within one transaction, manage enabling/disabling the filter at a clear boundary so one request's condition does not leak into subsequent operations.

A filter has no effect unless enabled, unless the Hibernate version and filter configuration support auto-enabling. You can attach a filter to multiple entities or collections, but each mapping must declare the corresponding filter.

### 6.1. Filters and loading entities by primary key

This is an important distinction when choosing `@Filter` for data that must remain hidden:

- In Hibernate 5.6, filters apply to entity queries but do not apply by default when loading an entity directly via `EntityManager.find()` or when resolving an association by primary key.
- Hibernate 6.6 documentation includes `@FilterDef(applyToLoadByKey = true)`. The default remains `false`; this option is marked incubating in the 6.6 Javadocs.
- In newer versions, check the exact Javadocs and test `find()`, lazy to-one associations, and entity queries. When a filter excludes a row referenced by a to-one association, Hibernate may throw `EntityFilterException` rather than behaving like a regular query.

Therefore, `@Filter` should not be the sole protective layer hiding sensitive data. When used for tenancy or access control, verify every data-loading path, including repository `findById`, `getReference`, lazy associations, native SQL, and queries executed by other applications.

## 7. Which Mechanism Should You Choose for Each Need?

| Need | Suitable Choice | Reason |
| --- | --- | --- |
| `remove()` must update a delete flag and regular queries skip deleted rows | `@SoftDelete` from Hibernate 6.4 | Hibernate manages both delete operations and read conditions |
| Hibernate 5.6–6.2 project needing soft delete | `@SQLDelete` + `@Where` | Compatible with versions prior to `@SoftDelete` |
| Hibernate 6.3 project needing a static restriction | `@SQLRestriction`; pair with `@SQLDelete` for soft delete | Replaces deprecated `@Where` |
| Filtering by tenant/status/time varying per Session | `@Filter` | Supports runtime parameters and per-Session toggling |
| Fixed condition on entity/collection without parameters | `@SQLRestriction` | Always applied without managing enable/disable |
| Filtering rows specifically in a join table | `@SQLJoinTableRestriction` or `@FilterJoinTable` | Condition is placed on the join table |
| Needing to restore deleted rows | Dedicated restore flow with permission checks | Soft-delete mechanisms do not provide a general undelete API |

A common design is `@SoftDelete` for the deletion lifecycle combined with `@Filter` for tenant scope or visibility status. When combining them, inspect the final generated SQL to ensure both conditions apply as intended.

## 8. Using Filters for Tenancy and Data Scoping

A tenant filter can be declared as:

```java
@FilterDef(
    name = "tenantScope",
    parameters = @ParamDef(name = "tenantId", type = Long.class)
)
@Filter(
    name = "tenantScope",
    condition = "tenant_id = :tenantId"
)
@Entity
@Table(name = "documents")
public class Document {
    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;
}
```

Before querying, the application enables `tenantScope` and takes the tenant ID from the authenticated principal/security context. Never accept a tenant ID from a query parameter and trust it directly. A filter is a helper layer for SQL generation; authorization must still be enforced in the service/security layer, and native queries or other access paths must also be protected.

For a filter shared within a Session, set the tenant parameter once at the transaction/request boundary. If the application uses Open Session in View or long-lived Sessions, ensure a Session never carries tenant/filter state from one request into another.

## 9. Limitations of Soft Delete in Relationships and Entity Lifecycle

Because soft delete keeps rows in the database, it affects rules that normally rely on physical row removal:

- Foreign keys still reference soft-deleted rows; the database does not automatically treat those rows as gone.
- `CascadeType.REMOVE` and `orphanRemoval = true` must be tested with soft-delete mappings. Child entities are soft-deleted only if the child entity's mapping also supports that mechanism; never assume a parent flag cascades automatically to all tables.
- `@SoftDelete` on `@ManyToMany` marks rows in the join table; it does not soft-delete the entity on the other side.
- For `@OneToMany`, place `@SoftDelete` on the child entity if you want children soft-deleted; do not attach the annotation directly to the `@OneToMany` collection.
- Native SQL queries, direct JDBC, or reporting tools outside Hibernate do not automatically inherit restriction/filter mappings.

If a soft-deleted parent means children must not appear on screen, decide explicitly whether that rule lives on the child's mapping, query joins, service predicates, or filters. Do not let each screen add conditions inconsistently.

## 10. Schema, Unique Constraints, and Indexes

Before enabling soft delete, prepare the schema with controlled migrations:

1. Add a boolean/bit `deleted` column (or suitable type) with `NOT NULL` and a default indicating active/not deleted.
2. Backfill all existing rows to the active state.
3. Update mappings and test INSERT/UPDATE/DELETE SQL.
4. Check indexes on commonly queried predicates, such as `deleted` combined with tenant or status.
5. Consider partial/filtered unique indexes if unique values only need to be unique among non-deleted rows.

Existing unique constraints still see soft-deleted rows. For example, if `email` has a table-wide unique constraint, soft-deleting an account does not automatically allow creating a new account with the same email. A partial unique index applying only to `deleted = false` is a solution on some databases, though syntax and support vary; do not assume it is portable.

Do not use `columnDefinition` in entities as a substitute for production schema migrations. Manage defaults, check constraints, indexes, and data backfills with your project's migration tool.

## 11. Restoration, Auditing, and Querying Deleted Data

`@SoftDelete` primarily standardizes marking rows deleted and excluding them from normal Hibernate queries. It does not provide a universal restore API for every use case.

If restoration is needed:

- Create a dedicated admin use case with authorization and auditing.
- Use controlled update statements to flip the deletion state; with Hibernate mappings, account for caches/persistence context and refresh/clear after native operations.
- Verify unique constraints, associations, and related state before restoring.
- Record who restored it, when, and why if business rules require it.

If querying deleted data is needed, create an explicit admin repository/query or use a controlled native SQL/reporting path. Never disable all filters/restrictions haphazardly during regular user requests.

Soft delete is not an audit log. If you need before/after history across multiple updates, actor tracking, and revisions, use audit tables or a solution such as Hibernate Envers. The `TIMESTAMP` strategy in Hibernate 7.x can record deletion time, but does not store who performed it or the reason.

## 12. Bulk DML and Native SQL Require Separate Verification

Never assume every write path goes through the same lifecycle:

- `EntityManager.remove(entity)` goes through the entity lifecycle and is the path to test when using `@SoftDelete` or `@SQLDelete`.
- Bulk JPQL/HQL `DELETE`, native `DELETE`, and direct JDBC may bypass per-entity removal mechanisms. Inspect actual SQL; if bulk soft deletion is needed, use an explicit conditional `UPDATE` or a bulk mechanism verified for your Hibernate version.
- Native SELECTs do not automatically apply `@Filter` or `@SQLRestriction`; add the necessary predicates manually.
- Bulk UPDATE/DELETE can leave loaded entities in the persistence context stale. Clear or refresh appropriately after bulk DML.

For bulk delete jobs, verify affected row counts, optimistic/version semantics, caching, and foreign keys. Never infer from a repository method name whether the SQL is UPDATE or DELETE.

## 13. Testing `@SoftDelete`

At minimum, tests should verify that `remove()` keeps the row in the database while normal entity queries no longer return it. Example for Hibernate 6.4+ with a boolean `deleted` column:

```java
package com.example.learning.document;

import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class DocumentSoftDeleteTest {
    @Autowired
    private EntityManager entityManager;

    @Test
    void removeMarksDocumentDeletedButKeepsDatabaseRow() {
        Document document = new Document("Hibernate guide");
        entityManager.persist(document);
        entityManager.flush();
        Long id = document.getId();

        entityManager.remove(document);
        entityManager.flush();
        entityManager.clear();

        assertThat(entityManager.find(Document.class, id)).isNull();

        Number rowCount = (Number) entityManager.createNativeQuery(
            "select count(*) from documents where id = :id and deleted = true"
        ).setParameter("id", id).getSingleResult();

        assertThat(rowCount.longValue()).isEqualTo(1L);
    }
}
```

This test assumes the entity has a `Document(String title)` constructor, a `getId()` getter, a `documents` table, and a boolean `deleted` column. Native SQL uses the test database's boolean syntax; if the database uses `BIT`, `NUMBER`, or another type, adjust the predicate to match the dialect. `@DataJpaTest` normally runs inside a test transaction; data rolls back when the test finishes.

## 14. Testing `@Filter` and Loading by ID

For filters, test both states: filter disabled and filter enabled. Beyond JPQL queries, test `EntityManager.find()` and lazy to-one associations:

```java
Session session = entityManager.unwrap(Session.class);

List<Document> allWithoutFilter = entityManager.createQuery(
    "select d from Document d", Document.class
).getResultList();

session.enableFilter("documentStatus").setParameter("status", "PUBLISHED");
List<Document> published = entityManager.createQuery(
    "select d from Document d", Document.class
).getResultList();
session.disableFilter("documentStatus");
```

This is an illustrative fragment requiring fixtures with multiple statuses and an entity declaring `@FilterDef`/`@Filter`. Add assertions for counts before and after enabling the filter. In older versions, verify that `find()` by ID may bypass the filter. In Hibernate 6.6+, if using `applyToLoadByKey = true`, also test the case where a to-one association target is excluded by the filter.

For soft delete, add tests for:

- Loading via repository `findById` after soft deletion.
- JPQL queries, lazy collection loading, and association joins.
- Cascade remove/orphan removal.
- Native queries and bulk DML.
- Restoration, unique constraints, and caching if those use cases are supported.

Run integration tests on the same database engine and driver as production, ideally using Testcontainers. H2 can differ from the production database in boolean types, partial indexes, custom SQL, constraints, and query optimization.

## 15. Migration Path from `@SQLDelete` to `@SoftDelete`

When upgrading a project from Hibernate 5.6/6.2 to 6.4+, you can migrate mappings entity by entity:

1. Inventory `@SQLDelete`, `@Where`, `@WhereJoinTable`, `@Filter`, and repositories manually appending `deleted = false`.
2. Verify the current column semantics: whether `true` means deleted or active; check for nulls and historical data.
3. Choose `SoftDeleteType.DELETED` or `ACTIVE` to match existing data; configure `columnName` and a converter if needed.
4. Add `@SoftDelete` on the appropriate entity or hierarchy root; do not keep old `@SQLDelete` annotations for the same operation if they conflict with the new mechanism.
5. Remove redundant manual restrictions once you verify `@SoftDelete` filters properly.
6. Keep `@Filter` for independent dynamic conditions such as tenant or status; do not remove filters simply because soft delete was added.
7. Test queries by ID, associations, collections, bulk DML, native SQL, cascades, and restoration.
8. Deploy schema migrations and monitor marked row counts, slow queries, and constraint errors.

For Hibernate 6.3, move `@Where` to `@SQLRestriction` where appropriate while keeping `@SQLDelete` if soft delete is required; `@SQLRestriction` does not replace delete operations.

## 16. Common Pitfalls

- **Using `@SoftDelete` on Hibernate prior to 6.4.** The annotation does not exist yet; use a compatible fallback or upgrade.
- **Using `@Where` in Hibernate 6.3+.** The annotation is deprecated; migrate to `@SQLRestriction` for static predicates.
- **Declaring only `@SQLDelete`.** Marked rows can still appear unless an appropriate restriction or query predicate is present.
- **Declaring only `@Where`/`@SQLRestriction`.** A restriction does not turn DELETE into UPDATE.
- **Using `@Filter` but forgetting to enable it.** Filters are inactive by default unless enabled or configured with suitable auto-enable behavior.
- **Assuming `@Filter` always applies to `find(id)`.** Direct fetching by primary key may ignore filters; check `applyToLoadByKey` and your version.
- **Using filters as the sole authorization boundary.** Native SQL, ID-based loads, and disabled filters can bypass conditions; authorization must be enforced on the server.
- **Placing `@SoftDelete` directly on a `@OneToMany` collection.** This mapping is unsupported; mark soft delete on the child entity.
- **Forgetting that `@SQLRestriction` is native SQL without parameters.** Use `@Filter` when runtime conditions are needed.
- **Wrong placeholders in `@SQLDelete`.** SQL must have the exact count and order of parameters Hibernate expects, especially with composite keys or `@Version`.
- **Assuming unique constraints ignore deleted rows.** Standard unique indexes still include soft-deleted rows.
- **Assuming soft delete automatically provides auditing/restore.** Dedicated use cases are needed for restoration and auditing.
- **Failing to test bulk DML/native SQL.** These paths may not follow per-entity deletion lifecycles.

## 17. Selection and Implementation Checklist

- [ ] Determined whether the requirement is soft delete or runtime data filtering.
- [ ] Checked actual Hibernate version and corresponding `javax`/`jakarta` imports.
- [ ] Hibernate 6.4+ uses `@SoftDelete` when entity/collection mapping is supported.
- [ ] Hibernate 5.6–6.2 uses `@SQLDelete` + `@Where` fallback when soft delete is required.
- [ ] Hibernate 6.3+ uses `@SQLRestriction` instead of `@Where` for static predicates.
- [ ] `@Filter` is enabled and parameterized within the right Session/transaction.
- [ ] Checked ID-based and association loading paths, including `applyToLoadByKey` if supported.
- [ ] Schema has a non-null status column, default, and suitable indexes.
- [ ] Evaluated unique constraints, foreign keys, cascades, and orphan removal.
- [ ] Native SQL and bulk DML include appropriate predicates or UPDATEs.
- [ ] Tests exist for remove, normal queries, `findById`, collections, filters, restoration, and caching.
- [ ] Integration tests run against a production-compatible database.

## Conclusion

Choose the mechanism according to the exact requirement and Hibernate version. Hibernate 6.4+ offers `@SoftDelete` to manage soft deletion; Hibernate 5.6–6.2 typically requires `@SQLDelete` paired with `@Where`; from 6.3 onward, use `@SQLRestriction` instead of `@Where` for static predicates. `@Filter` is meant for dynamic Session-enabled conditions and requires careful attention to the difference between entity queries and primary-key loads. Verify schemas, associations, unique constraints, bulk/native SQL, and test on the target database before shipping mappings to production.

## Official Documentation

- [Hibernate ORM 5.6 User Guide – Filtering entities and associations](https://docs.hibernate.org/orm/5.6/userguide/html_single/)
- [Hibernate ORM 6.3 `@Where` Javadocs – deprecated in favor of `SQLRestriction`](https://docs.hibernate.org/orm/6.3/javadocs/org/hibernate/annotations/Where.html)
- [Hibernate ORM 6.3 `@SQLRestriction` Javadocs](https://docs.hibernate.org/orm/6.3/javadocs/org/hibernate/annotations/SQLRestriction.html)
- [Hibernate ORM 6.4 User Guide – `@SoftDelete`](https://docs.hibernate.org/orm/6.4/userguide/html_single/)
- [Hibernate ORM 6.4 Migration Guide – soft delete added in 6.4](https://docs.hibernate.org/orm/6.4/migration-guide/)
- [Hibernate ORM 6.6 `@FilterDef` Javadocs – `applyToLoadByKey`](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/annotations/FilterDef.html)
- [Hibernate ORM current User Guide – soft delete and filters](https://docs.hibernate.org/orm/current/userguide/html_single/)