# Soft Delete, Filtering, and Post-Delete Uniqueness in Hibernate

Soft delete marks a record as deleted instead of physically removing it from the database. The row remains in place for restoration, auditing, or historical reconciliation, while normal business queries must hide it from results.

When implementing soft delete, three problems must be solved together:

1. **Deletion:** application delete operations must update the deletion state instead of issuing a physical DELETE.
2. **Filtering:** regular queries must exclude deleted records; administration screens may need to view or restore them.
3. **Uniqueness:** after a record is soft-deleted, should a business key such as SKU, email, or username be allowed to be reused?

Simply adding a deleted column and filtering in a few repository methods is not enough. A single query missing the condition can cause deleted data to reappear. A standard unique constraint can prevent creating a new record even though the old one was soft-deleted. Conversely, dropping the unique constraint to allow key reuse can create two active duplicate records if there is no proper database constraint.

This lesson covers Hibernate's options, data filtering, restoration rules, database-specific unique indexes, impact on relationships and bulk queries, and testing against a real database.

## 1. Physical Delete vs. Soft Delete

Physical deletion uses SQL DELETE to remove the row from the table:

~~~sql
DELETE FROM products WHERE id = 42;
~~~

Once the transaction commits, the row is no longer in the table. Without backups or a separate audit trail, recovery can be difficult.

Soft deletion uses UPDATE to mark the row:

~~~sql
UPDATE products
SET deleted = true,
    deleted_at = CURRENT_TIMESTAMP
WHERE id = 42;
~~~

The row still exists, but it is treated as no longer active. Normal queries must filter it out:

~~~sql
SELECT *
FROM products
WHERE deleted = false;
~~~

Another design uses deleted_at:

- deleted_at IS NULL: active record.
- deleted_at IS NOT NULL: soft-deleted record.

A timestamp column records when deletion occurred and is often useful for auditing. A boolean column is simpler if only the status is needed. Both can be used together for fast status filtering and timestamp recording.

Soft delete does not replace backups, audit logs, or retention policies. It only keeps rows in the operational table and changes how the application perceives them.

## 2. Define Business Policy Before Choosing a Mapping

Before writing annotations, clarify:

- Who is allowed to soft-delete?
- Is restoration allowed?
- Are regular users allowed to view deleted records?
- Can a business key be reused after deletion?
- If restoring a record whose key is already taken by another active record, how should it be handled?
- Do we need to store who deleted it, the reason, and the timestamp?
- Does deleting a parent soft-delete its children?
- Is physical deletion required after a retention period?
- Do external writers update the table directly outside the application?

There is no single policy suitable for every domain. For example, usernames may be retained permanently to prevent identity hijacking; SKUs of discontinued items may be reusable under policy; invoice numbers typically should not be reused to preserve historical uniqueness.

The uniqueness policy must be decided before creating indexes. Otherwise, the system might implement soft delete successfully yet fail to recreate records with the same business key.

## 3. Example Data Model

The example uses Product with SKU as the business key. Soft-deleted records do not appear in active product listings. We use a boolean deleted field and a deleted_at timestamp for the manual mapping variant.

~~~java
package com.example.product;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 80)
    private String sku;

    @Column(nullable = false, length = 200)
    private String name;

    @Column(nullable = false)
    private boolean deleted;

    private Instant deletedAt;

    protected Product() {
    }

    public Product(String sku, String name) {
        this.sku = sku;
        this.name = name;
        this.deleted = false;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public boolean isDeleted() {
        return deleted;
    }

    public Instant getDeletedAt() {
        return deletedAt;
    }
}
~~~

Do not declare unique = true on SKU in this example because the desired policy is that the SKU can be reused after the old record is soft-deleted. An appropriate unique index will be created separately in the database to apply only to active rows.

In production, manage schemas with migrations such as Flyway or Liquibase. Do not rely on hibernate.ddl-auto=update to create filtered/partial indexes because syntax and support vary by database.

## 4. Hibernate @SoftDelete

Starting with Hibernate ORM 6.4, you can use the @SoftDelete annotation to declare soft delete at the entity level. Hibernate automatically converts remove operations into updates on an indicator column and automatically applies conditions to exclude deleted records when loading entities through the ORM.

Example:

~~~java
package com.example.product;

import java.math.BigDecimal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import org.hibernate.annotations.SoftDelete;
import org.hibernate.annotations.SoftDeleteType;

@Entity
@Table(name = "catalog_products")
@SoftDelete(
    strategy = SoftDeleteType.DELETED,
    columnName = "deleted"
)
public class CatalogProduct {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 80)
    private String sku;

    @Column(nullable = false, length = 200)
    private String name;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal price;

    protected CatalogProduct() {
    }

    public CatalogProduct(String sku, String name, BigDecimal price) {
        this.sku = sku;
        this.name = name;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
~~~

With the DELETED strategy, the indicator value represents a deleted record; Hibernate's default indicator column name is deleted unless configured otherwise. The example sets columnName explicitly so the schema is clear to read.

Hibernate @SoftDelete is a Hibernate-specific feature, not a standard Jakarta Persistence annotation. The project must use Hibernate ORM 6.4 or higher and import org.hibernate.annotations.SoftDelete and SoftDeleteType. Check the exact dependency version before copying the example.

With this mapping, calling EntityManager.remove(entity) or repository.delete(entity) goes through Hibernate's soft-delete mechanism instead of physically deleting the row by default. Normal Hibernate entity queries automatically exclude rows marked as deleted according to the mapping.

Do not add an independent boolean deleted property and expect it to stay in sync with @SoftDelete without proper mapping configuration. The annotation manages the indicator column; decide explicitly how to access the status and how to read deleted records.

## 5. SoftDeleteType.DELETED and ACTIVE

Hibernate provides two ways to interpret the indicator:

- DELETED: true indicates the record is deleted.
- ACTIVE: true indicates the record is active.

ACTIVE example:

~~~java
@SoftDelete(
    strategy = SoftDeleteType.ACTIVE,
    columnName = "active"
)
@Entity
@Table(name = "catalog_products")
public class CatalogProduct {
    // Entity properties.
}
~~~

With ACTIVE, Hibernate writes the indicator state using the active meaning. Schema and migrations must consistently reflect that interpretation; do not name a column active while writing an index predicate using the deleted meaning.

Choose a single convention across the entire application. With a deleted column, the DELETED strategy is usually easier to read: false means active, true means deleted.

## 6. Manual Mapping with @SQLDelete and @SQLRestriction

Before Hibernate 6.4, or when fine-grained SQL control is needed, you can use @SQLDelete to replace DELETE statements with UPDATE, and @SQLRestriction to add a static filter condition.

~~~java
package com.example.product;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import org.hibernate.annotations.SQLDelete;
import org.hibernate.annotations.SQLRestriction;

@Entity
@Table(name = "products")
@SQLDelete(
    sql = """
          UPDATE products
          SET deleted = true,
              deleted_at = CURRENT_TIMESTAMP
          WHERE id = ?
          """
)
@SQLRestriction("deleted = false")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 80)
    private String sku;

    @Column(nullable = false, length = 200)
    private String name;

    @Column(nullable = false)
    private boolean deleted;

    @Column(name = "deleted_at")
    private Instant deletedAt;

    protected Product() {
    }

    public Product(String sku, String name) {
        this.sku = sku;
        this.name = name;
        this.deleted = false;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public boolean isDeleted() {
        return deleted;
    }

    public Instant getDeletedAt() {
        return deletedAt;
    }
}
~~~

The two annotations have distinct roles:

- @SQLDelete replaces the SQL Hibernate emits when deleting an entity.
- @SQLRestriction adds a fixed SQL predicate to queries loading the corresponding entity or collection.

@SQLRestriction uses a SQL fragment referencing physical column names—in this example, deleted. It is not JPQL and does not use Java property names if the column name differs.

The example above does not include @Version. If the entity uses optimistic locking with a version column, the custom SQL must accept the exact bind parameters Hibernate passes according to the mapping, including version in the order required by the provider. Check the SQL for your exact Hibernate version and test row-count/optimistic-lock behavior; never copy SQL without a version parameter verbatim into a @Version entity.

In newer Hibernate versions, the older @Where annotation has been replaced/deprecated; prefer @SQLRestriction when supported by your version. For older Hibernate versions, check the API available in your project's version.

## 7. Choosing @SoftDelete or Manual Mapping?

| Criterion | @SoftDelete | @SQLDelete + @SQLRestriction |
|---|---|---|
| Version | Hibernate ORM 6.4+ | Available in earlier Hibernate versions |
| Configuration | Concise, indicator-column driven | Requires writing delete SQL and restriction manually |
| Delete SQL | Managed by Hibernate | Application declares explicit SQL |
| Filtering deleted records | Integrated into Hibernate's soft-delete mapping | Static restriction appended to queries |
| Deletion timestamp | Indicator managed by Hibernate | Can update timestamp/audit columns directly |
| SQL control | Less granular | Full control over the UPDATE statement |
| Risks | Depends on Hibernate version | Incorrect placeholders, version, or row-count in custom SQL |

If your project uses Hibernate 6.4+, @SoftDelete is usually the simplest starting point. If you need custom SQL, timestamps, or are on an older version, choose @SQLDelete and a restriction.

Do not attach both strategies to the same entity without understanding their interaction. Choose one soft-delete mechanism as the source of truth for the indicator column.

## 8. @SQLRestriction Is a Static Filter

@SQLRestriction always appends a condition to corresponding ORM queries. With:

~~~java
@SQLRestriction("deleted = false")
~~~

normal queries reading Product exclude rows with deleted = true.

Key characteristics:

- The restriction has no toggle parameters.
- It cannot be temporarily disabled like a Hibernate filter.
- It does not automatically inject conditions into every SQL statement written manually by the application.
- Native SQL, JDBC, stored procedures, and queries from external applications must enforce the policy themselves.
- Admin queries that need to view deleted records must use a separate, controlled access path.

This is a good choice when nearly every ORM operation must hide deleted records and there is no need to toggle the filter within the same persistence context.

If there are restoration or audit use cases that need to read deleted records, design an explicit administrative access path. Do not try to work around the restriction by modifying SQL ad hoc in a regular endpoint.

## 9. Using @Filter When Dynamic Toggling Is Needed

Hibernate @Filter allows applying parameterized conditions and enabling/disabling them per Session. It fits when the same application has regular user flows seeing only active records and administrative flows permitted to see deleted records as well.

Example:

~~~java
package com.example.product;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import org.hibernate.annotations.Filter;
import org.hibernate.annotations.FilterDef;
import org.hibernate.annotations.ParamDef;

@Entity
@Table(name = "products")
@FilterDef(
    name = "productVisibility",
    parameters = @ParamDef(name = "includeDeleted", type = Boolean.class),
    applyToLoadByKey = true
)
@Filter(
    name = "productVisibility",
    condition = "deleted = false or :includeDeleted = true"
)
public class FilteredProduct {
    @Id
    private Long id;

    // Remaining properties.
}
~~~

Enabling the filter in a transaction:

~~~java
import org.hibernate.Session;

Session session = entityManager.unwrap(Session.class);

session.enableFilter("productVisibility")
        .setParameter("includeDeleted", false);
~~~

Administrative flows can enable includeDeleted = true in a separate, permission-restricted Session. Filters are a Hibernate feature; applyToLoadByKey is available in Hibernate versions that support this attribute. If your project's version lacks that attribute, omit it and verify load-by-identifier behavior separately.

Do not rely on a filter as the sole security boundary. Test findById, getReference, association loading, JPQL queries, native SQL, and administrative paths. If a filter is not enabled in a new Session, queries may run without the expected condition.

Do not combine @SQLRestriction deleted=false and @Filter with includeDeleted=true on the same entity expecting the filter to expose deleted records again; the static restriction always applies. Choose either static restriction or dynamic filter based on your needs.

## 10. Manual Filtering at the Repository Layer

A straightforward approach is mapping deleted as a property and adding conditions to each method:

~~~java
public interface ProductRepository extends JpaRepository<Product, Long> {

    Optional<Product> findBySkuAndDeletedFalse(String sku);

    List<Product> findAllByDeletedFalse();

    boolean existsBySkuAndDeletedFalse(String sku);
}
~~~

This approach is easy to understand, but easy to overlook as a repository grows. Inherited methods such as findById from JpaRepository do not automatically add DeletedFalse without a Hibernate restriction or filter.

If using manual filtering, establish clear conventions, review every new method, and avoid calling JpaRepository directly from controllers. Route queries through dedicated services/repositories so one place is responsible for applying active predicates.

Do not assume simply naming a method findActive... guarantees every query is safe. Inspect the SQL and test each read path.

## 11. Repository Methods for Soft Delete and Restore

With manual mapping that includes a deleted property, you can write explicit update methods:

~~~java
package com.example.product;

import java.time.Instant;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    Optional<Product> findBySkuAndDeletedFalse(String sku);

    boolean existsBySkuAndDeletedFalse(String sku);

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Transactional
    @Query("""
           update Product p
           set p.deleted = true,
               p.deletedAt = :deletedAt
           where p.id = :id
             and p.deleted = false
           """)
    int markDeleted(
            @Param("id") Long id,
            @Param("deletedAt") Instant deletedAt);

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Transactional
    @Query("""
           update Product p
           set p.deleted = false,
               p.deletedAt = null
           where p.id = :id
             and p.deleted = true
           """)
    int restore(
            @Param("id") Long id);
}
~~~

This updates the deleted property directly without relying on @SQLDelete. Use markDeleted/restore only if the entity is mapped with deleted and deletedAt as in the manual example.

If the entity uses @SQLRestriction deleted=false, JPQL update queries may be affected by the restriction depending on Hibernate/provider and query type. Check the generated SQL. A reliable restore path can use a native UPDATE by ID or a separate administrative repository without the restriction, after verifying unique constraints.

Bulk updates do not synchronize the state of managed entities in the persistence context. clearAutomatically=true clears the persistence context after the update; flushAutomatically=true flushes pending changes before running the bulk query. Use them intentionally, as clear detaches other entities in the same context.

## 12. Not Every DELETE Goes Through the Same Mechanism

Distinguish among:

- EntityManager.remove(entity): removes a single managed entity.
- JpaRepository.delete(entity): typically delegates to removing via EntityManager.
- JpaRepository.deleteById(id): Spring Data's implementation typically loads the entity and removes it.
- Bulk JPQL DELETE with @Modifying: executes a bulk statement directly without loading and removing each entity.
- Native SQL DELETE/JDBC/stored procedures: goes straight to the database.

@SoftDelete and @SQLDelete are designed around Hibernate's entity removal mechanism. Never assume bulk JPQL DELETE, native DELETE, or external SQL automatically turns into a soft delete like entity.remove().

When bulk soft deletion is needed, write an explicit UPDATE:

~~~java
@Modifying(clearAutomatically = true, flushAutomatically = true)
@Transactional
@Query("""
       update Product p
       set p.deleted = true,
           p.deletedAt = :now
       where p.deleted = false
         and p.id in :ids
       """)
int softDeleteAllByIds(
        @Param("ids") Collection<Long> ids,
        @Param("now") Instant now);
~~~

This requires manual mapping with deleted/deletedAt. If using @SoftDelete with a Hibernate-managed indicator, do not assume a deleted property exists in JPQL; use supported APIs/SQL and test against your Hibernate version.

Do not call deleteAllInBatch or write native DELETE if the business requirement is to retain deleted rows. Test the actual SQL to verify whether the database receives UPDATE or DELETE.

## 13. Standard Unique Constraints Still Hold Keys After Soft Delete

Suppose the database has:

~~~sql
ALTER TABLE products
ADD CONSTRAINT uk_products_sku UNIQUE (sku);
~~~

After Product SKU-100 is soft-deleted, the row remains in the table. When creating a new Product with the same SKU-100, the unique constraint still sees the old row and rejects the INSERT.

This follows standard unique constraint semantics. The database does not know the application considers that row deleted unless uniqueness is explicitly designed to apply only to active rows.

Do not drop the unique constraint and rely solely on code-level checks:

~~~java
if (!repository.existsBySkuAndDeletedFalse(sku)) {
    repository.save(new Product(sku, name));
}
~~~

Two concurrent transactions can both pass the existence check and both execute INSERT. Pre-checking only improves error messages; a database constraint is the final safeguard for uniqueness.

## 14. Unique Indexes Applying Only to Active Records

If SKUs are allowed to be reused after deletion, a conditional unique index is needed:

- Rows with deleted = false must have unique SKUs.
- Rows with deleted = true do not participate in that uniqueness constraint.

Implementation depends on the database. There is no single portable DDL statement across all RDBMSs.

### PostgreSQL: partial unique index

~~~sql
CREATE UNIQUE INDEX uq_products_active_sku
ON products (sku)
WHERE deleted = false;
~~~

Only rows with deleted=false participate in the index. Multiple deleted rows can retain the same SKU while active rows remain unique.

If SKU is unique per tenant:

~~~sql
CREATE UNIQUE INDEX uq_products_active_tenant_sku
ON products (tenant_id, sku)
WHERE deleted = false;
~~~

### SQL Server: filtered unique index

~~~sql
CREATE UNIQUE INDEX uq_products_active_sku
ON dbo.products (sku)
WHERE deleted = 0;
~~~

The filter predicate includes only active rows. Boolean/bit syntax and schema names depend on your SQL Server design.

### MySQL: generated column and unique index

MySQL does not offer partial indexes with a WHERE clause like PostgreSQL. You can create a generated column that holds the SKU when active and NULL when deleted:

~~~sql
ALTER TABLE products
ADD COLUMN active_sku VARCHAR(80)
GENERATED ALWAYS AS (
    CASE WHEN deleted = 0 THEN sku ELSE NULL END
) STORED;

CREATE UNIQUE INDEX uq_products_active_sku
ON products (active_sku);
~~~

A unique index allows multiple NULL values in MySQL, so deleted rows do not conflict via active_sku. Verify your MySQL version, collation, column types, and NULL rules before applying.

Do not reuse the exact same DDL across different databases. Run migrations on the actual production database engine and verify execution plans/index metadata after deployment.

## 15. Why unique(deleted, sku) Is Usually Not the Right Solution

An intuitive idea is:

~~~sql
ALTER TABLE products
ADD CONSTRAINT uq_products_deleted_sku
UNIQUE (deleted, sku);
~~~

This allows one row with deleted=false and one row with deleted=true to share the same SKU. However, it permits only one deleted=true row per SKU. If a SKU is reused and deleted multiple times, the second soft delete conflicts with the previous deleted=true row.

Example:

| id | sku | deleted |
|---:|---|---|
| 1 | SKU-100 | true |
| 2 | SKU-100 | false |

When deleting row id=2, the second row becomes deleted=true and produces the pair (true, SKU-100), colliding with row id=1.

Therefore, unique(deleted, sku) fails to express "unique only among active records" when multiple deleted versions may exist. A partial/filtered unique index or a generated active key is much better suited.

## 16. Tenant-Scoped Business Keys

If each tenant is allowed to use the same SKU, uniqueness must include tenant_id:

~~~sql
CREATE UNIQUE INDEX uq_products_active_tenant_sku
ON products (tenant_id, sku)
WHERE deleted = false;
~~~

With MySQL, you can create a generated active_sku as shown earlier and create a unique index on (tenant_id, active_sku).

The application layer must use the same scope:

~~~java
boolean existsByTenantIdAndSkuAndDeletedFalse(
        Long tenantId,
        String sku);
~~~

Do not check SKU globally if the database allows duplicate SKUs across tenants. Conversely, do not key caches or lookup APIs solely by SKU when data is partitioned by tenant.

Every query, unique index, cache key, and restore operation must agree on the exact same business key definition.

## 17. Recreating a Record After Soft Delete

A creation flow can check beforehand to return a friendly error:

~~~java
@Transactional
public Product create(String sku, String name) {
    if (repository.existsBySkuAndDeletedFalse(sku)) {
        throw new DuplicateActiveSkuException(sku);
    }

    return repository.save(new Product(sku, name));
}
~~~

However, existsBySkuAndDeletedFalse does not replace the unique index. If two requests attempt to create the same SKU concurrently, one transaction can win while the other receives a constraint violation.

Catch DataIntegrityViolationException at the appropriate service boundary, distinguish the SKU unique violation from other constraint errors if needed, and translate it into an appropriate business response. Do not swallow every DataIntegrityViolationException and report a duplicate SKU when the real cause is a foreign key or NOT NULL violation.

## 18. Restoring a Deleted Record Can Trigger Uniqueness Conflicts

Suppose:

1. Product id=1, SKU-100 is soft-deleted.
2. A new Product id=2 is created with SKU-100.
3. An administrator attempts to restore id=1.

If the unique index applies only to active records, restoring id=1 will conflict with id=2. This is the correct outcome: there cannot be two active products with the same SKU.

A restore policy must be defined:

- Reject the restoration and require choosing another SKU.
- Restore after renaming the old record's SKU.
- Merge historical data into the active record.
- Restore via an audited administrative workflow with validation.

Do not temporarily drop the unique index just to restore. Let the database enforce the invariant and handle the constraint error as a clear business outcome.

## 19. Race Conditions Across Delete, Create, and Restore

The following operations may run concurrently:

- Request A checks that a SKU does not exist and creates it.
- Request B restores an old row with the same SKU.
- Request C soft-deletes an active row.
- Job D runs a bulk import.

If relying solely on Java-level checks, two transactions can pass the check simultaneously. A conditional unique index enforces uniqueness atomically in the database.

Principles:

- The unique index is the source of truth for uniqueness.
- exists queries are only for better error messages or avoiding guaranteed failures.
- Catch constraint errors within the transaction and translate them into domain errors.
- Do not retry indefinitely when the conflict is a business error.
- For bulk imports, define policies to skip, update, or reject individual records.
- Test with concurrent transactions if the workload has high contention.

If a workflow involves multi-step restore/rename operations, wrap it in a transaction and handle unique conflicts explicitly. Never rely on web request ordering to guarantee uniqueness.

## 20. Restoring with @SQLRestriction and @Filter

If an entity uses @SQLRestriction("deleted = false"), normal ORM queries cannot see deleted rows. Because a static restriction cannot be turned off, a standard repository method may not find the entity to restore it.

Options:

- A native UPDATE by ID setting deleted=false and deleted_at=NULL; the unique index checks for conflicts.
- A separate administrative entity/repository with a mapping suitable for reading deleted rows as well.
- Using Hibernate @Filter so includeDeleted can be enabled in a controlled Session.
- Using JDBC or a specialized administrative service for the restore workflow.

Example native restore for manual mapping:

~~~java
@Modifying
@Transactional
@Query(
    value = """
            UPDATE products
            SET deleted = false,
                deleted_at = NULL
            WHERE id = :id
              AND deleted = true
            """,
    nativeQuery = true
)
int restoreById(@Param("id") Long id);
~~~

Because this is native SQL, it does not use JPQL entity/property names. The method returns the number of updated rows: 1 means a deleted row was restored; 0 means the ID does not exist or is not in the deleted state. If the unique index detects the SKU is already in use, the database rejects the UPDATE and the transaction must treat it as a conflict.

With @SoftDelete, the indicator may be managed by Hibernate without a deleted property on the entity. Do not use JPQL update p.deleted if that property is not mapped. Use an administrative approach compatible with your Hibernate version/provider and test restoration on the target database.

## 21. Parent-Child Relationships and Cascades

Soft-deleting a parent entity does not automatically define the policy for child entities. Decide explicitly:

- Do children stay active even without a visible parent?
- Are children also soft-deleted?
- Are children moved to an archived state?
- Is only the join table link removed?
- Does child history need to be preserved for auditing?

CascadeType.REMOVE may invoke remove on child entities depending on mapping/provider. If children also have soft-delete mappings, the remove operation may translate into soft-deleting the children. However, never infer domain policy solely from cascade annotations.

orphanRemoval=true can trigger removal when an element is removed from a collection. If the child entity has a soft-delete mapping, verify whether the provider issues UPDATE or DELETE and how the collection is subsequently synchronized.

With ManyToMany, removing an element from the collection typically affects the join table; it does not automatically soft-delete the target entity. If membership history is needed, consider promoting the join table to a dedicated association entity with deleted/deletedAt.

Test remove, clear collection, delete parent, and restore parent operations on the real mapping. Never let cascading accidentally physically delete data that must be retained.

## 22. Unique Constraints on Associations and Other Fields

An entity may have multiple uniqueness rules:

- Unique SKU among active products.
- Unique email among active accounts.
- Unique external reference code per tenant.
- One active primary record per customer.
- One active membership type per user/team.

Each invariant should be represented by an appropriate index/constraint. For example, a customer can have only one active default address:

~~~sql
CREATE UNIQUE INDEX uq_customer_default_address
ON customer_addresses (customer_id)
WHERE is_default = true
  AND deleted = false;
~~~

This is a PostgreSQL-style partial index. Other databases require equivalent syntax such as filtered indexes or generated columns.

If uniqueness depends on multiple conditions, write an explicit index predicate and test edge cases. Do not rely on a global unique constraint if business rules require uniqueness only among non-deleted rows.

## 23. Soft Delete, Caching, and Search Data

When a Product is soft-deleted, caches and search indexes must also reflect the new state.

Points to handle:

- Evict detail caches by SKU/ID after commit.
- Evict or update list/search-result caches containing the product.
- Remove the document from the search index or mark it inactive.
- Ensure cache keys and queries return only active products.
- If a SKU is reused, prevent stale cache entries from the deleted record from serving incorrect content.
- On restore, refresh caches/indexes after commit.

Do not evict caches before the transaction commits if another request could read the old database state and repopulate the cache. You can publish domain events and handle invalidation after commit; for reliable delivery requirements, use an outbox/retry mechanism.

## 24. Auditing and Retention

Soft delete stores only the deletion state. Many systems also need to know who deleted the record, why, and whether/when it was restored.

You can add:

~~~java
@Column(name = "deleted_by")
private String deletedBy;

@Column(name = "deletion_reason", length = 500)
private String deletionReason;

@Column(name = "deleted_at")
private Instant deletedAt;
~~~

You do not necessarily have to put all audit metadata on the entity if the system already has a dedicated audit log. Distinguish between data representing current state and data representing event history.

A retention policy might specify:
- Soft-deleted records are retained for 90 days.
- After that period, a job archives or physically deletes them.
- Some data categories must be retained longer for compliance or reconciliation.
- Backups and audit logs have separate retention cycles.

Purge jobs must check dependent relationships, foreign keys, audit requirements, and legal policies before physical deletion. Never use a purge job to bypass uniqueness or substitute for a restore workflow.

## 25. Testing Basic Soft Delete

With manual @SQLDelete + @SQLRestriction mapping, tests must confirm that delete does not physically remove the row while regular ORM queries no longer return it.

Repository test example:

~~~java
package com.example.product;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class ProductSoftDeleteTest {

    @Autowired
    private ProductRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void deleteMarksRowAndHidesItFromNormalQueries() {
        Product product = new Product("SKU-100", "Keyboard");
        entityManager.persist(product);
        entityManager.flush();

        Long id = product.getId();

        repository.delete(product);
        entityManager.flush();
        entityManager.clear();

        assertThat(repository.findById(id)).isEmpty();

        Number deletedRows = (Number) entityManager.getEntityManager()
                .createNativeQuery("""
                    select count(*)
                    from products
                    where id = :id
                      and deleted = true
                    """)
                .setParameter("id", id)
                .getSingleResult();

        assertThat(deletedRows.longValue()).isEqualTo(1);
    }
}
~~~

The test uses a native query to verify the row still exists with deleted=true. Native queries are not parsed as JPQL and use physical table/column names. The test assumes the database has a boolean deleted column and @SQLDelete matching the manual mapping.

With Hibernate @SoftDelete, write an equivalent test on the catalog_products table and the configured indicator column. Test repository delete, EntityManager.remove, findById, and native SQL separately.

## 26. Testing Post-Delete Uniqueness

Uniqueness tests must run on the actual target database because partial/filtered indexes and generated columns differ across database engines.

Cases to cover:

1. Creating an active Product SKU-100 succeeds.
2. Creating another Product SKU-100 while the first is still active is rejected.
3. Soft-deleting the first record.
4. Creating a new Product SKU-100 succeeds if policy allows reuse.
5. Soft-deleting the second record.
6. Creating a third record with the same SKU succeeds.
7. Restoring the first record while the SKU is in use by the third record is rejected.
8. Restoring succeeds after the SKU becomes free.
9. Testing two concurrent transactions creating the same SKU to confirm the unique index protects the data.

H2 may not support the same partial index syntax as your production database. Use Testcontainers with PostgreSQL, SQL Server, or MySQL accordingly to verify migrations and real constraint behavior.

Do not test only existsBySkuAndDeletedFalse. Test the unique index directly, because race conditions cannot be proven by simple sequential tests.

## 27. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| delete still deletes physically | Entity lacks soft-delete mapping or another DELETE path is used | Inspect SQL and the remove mechanism |
| findById still sees deleted records | Missing filter/restriction or filter not enabled | Check @SoftDelete, @SQLRestriction, @Filter, and load-by-key |
| Native query returns deleted records | Native SQL does not automatically apply ORM predicates | Add deleted=false in SQL |
| SKU cannot be reused | Full unique constraint still counts deleted rows | Use partial/filtered index or generated active key |
| Second delete triggers unique conflict | UNIQUE(deleted, sku) allows only one deleted=true row | Use a proper conditional index |
| Restore fails | SKU is already in use by an active record | Handle business conflict |
| Two requests create duplicates | Checked exists only in Java without a unique index | Enforce the invariant in the database |
| Bulk DELETE removes rows physically | Bulk/native delete bypasses entity remove mapping | Use an explicit soft-delete UPDATE |
| Restore cannot find entity | @SQLRestriction always hides deleted rows | Use native/admin path or dynamic filter |
| Children deleted unintentionally | Inappropriate cascade/orphanRemoval | Define policy and test associations |
| Cache still serves deleted product | Missing post-commit invalidation | Evict/update cache and search index |
| Hibernate reports stale state on delete | Custom SQL has wrong placeholders/row count/version | Check @SQLDelete and optimistic locking |
| DDL works in dev but fails in production | Partial index syntax differs by database | Write dialect-specific migrations and test with real containers |

## 28. Safe Implementation Workflow

A practical rollout sequence:

1. Define policies for deletion, restoration, visibility permissions, and uniqueness.
2. Add the indicator column and required audit metadata.
3. Choose @SoftDelete or manual mapping suited to your Hibernate version.
4. Choose static restriction or dynamic filter for ORM queries.
5. Inventory every read path: repositories, findById, associations, native SQL, batch jobs, and other APIs.
6. Create partial/filtered unique indexes or generated active keys according to the database.
7. Implement services for delete/restore and handle unique conflicts.
8. Update caches/search indexes after commit.
9. Test entity removal, bulk operations, native queries, and association cascades.
10. Run migrations and uniqueness tests on the exact production database engine.
11. Monitor constraint errors, queries leaking deleted data, and retention durations.
12. Deploy a separate purge job if retention policy requires physical deletion after a deadline.

When migrating large tables, creating indexes can lock tables or consume heavy resources. Use online/concurrent index creation strategies appropriate for your database and deployment process.

## 29. Self-Assessment Checklist

- [ ] Distinguish physical DELETE from soft-delete UPDATE.
- [ ] Define policies for restore and business key reuse.
- [ ] Know that Hibernate @SoftDelete requires Hibernate ORM 6.4+.
- [ ] Distinguish SoftDeleteType.DELETED and ACTIVE.
- [ ] Understand @SQLDelete overrides remove SQL and @SQLRestriction filters statically.
- [ ] Know that @SQLRestriction cannot be disabled per request.
- [ ] Understand @Filter must be enabled per Session and tested for load-by-ID.
- [ ] Distinguish Spring Data entity delete from bulk JPQL/native DELETE.
- [ ] Never assume bulk DELETE automatically becomes soft delete.
- [ ] Know that native SQL must apply deleted conditions explicitly.
- [ ] Understand full unique constraints still hold keys of deleted rows.
- [ ] Know why UNIQUE(deleted, sku) fails under repeated reuse.
- [ ] Create partial/filtered unique indexes per database.
- [ ] Use generated active keys when the database does not support partial indexes.
- [ ] Include tenant in uniqueness if the business key is tenant-scoped.
- [ ] Rely on database constraints as the source of truth under concurrent writes.
- [ ] Handle conflicts on restore.
- [ ] Verify cascades, orphanRemoval, and join tables.
- [ ] Invalidate caches/search indexes after commit.
- [ ] Test on the same database engine used in production.

## 30. Conclusion

Soft delete changes a record's status rather than removing the row from the database. A sound implementation needs a mechanism to turn remove into update, consistent filtering rules across all read paths, and unique indexes aligned with your business key reuse policy.

Hibernate @SoftDelete is the built-in choice from Hibernate 6.4 onward; @SQLDelete combined with @SQLRestriction fits when custom SQL or older versions are needed. @Filter supports dynamic visibility, but must be managed per Session and verified for load-by-key. For uniqueness, use partial/filtered indexes or generated active keys to guard only active rows; Java-side pre-checks cannot replace database constraints.

Finally, clearly define restore, cascade, cache invalidation, and retention rules. Testing ORM paths, bulk/native SQL, concurrent contention, and migrations against the real database engine ensures deleted data never surfaces where it shouldn't and business keys remain unique according to policy.