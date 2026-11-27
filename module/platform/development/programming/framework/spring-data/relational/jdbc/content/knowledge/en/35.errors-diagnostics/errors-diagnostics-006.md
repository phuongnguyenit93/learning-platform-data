# save Chooses the Wrong Insert/Update or Fails to Retrieve the Generated Key

In Spring Data JDBC, the save method does not blindly run INSERT every time or UPDATE every time. Before generating SQL, Spring Data determines whether the aggregate root is **new** or **already existing**. If the aggregate is new, save generates an INSERT; if not new, save performs an UPDATE.

Consequently, when save chooses the wrong operation, the cause usually lies in entity state, how ID/version is declared, or how the application assigns IDs. When an INSERT succeeds without returning a generated key, inspect the mapping, schema, dialect, and JDBC driver.

This lesson explains how Spring Data JDBC detects new entities, how to configure auto-increment or sequence IDs, how to use Persistable for application-assigned IDs, and a diagnostic workflow when save takes the wrong branch or omits the generated ID.

## 1. How does save decide between INSERT and UPDATE?

Spring Data JDBC determines aggregate root state before building the SQL plan:

~~~text
repository.save(aggregate)
          |
          v
    Is aggregate new?
       /        \
     Yes         No
      |           |
      v           v
   INSERT       UPDATE
      |           |
      v           v
  Generated     Match existing
  key returned  aggregate row
~~~

If the aggregate is considered new:

- INSERT the aggregate root.
- INSERT directly or indirectly owned entities in the aggregate.
- The database may generate the root ID if the column is configured as auto-increment.
- Spring Data JDBC populates the generated ID into the returned instance.

If the aggregate is considered existing:

- UPDATE the aggregate root.
- Owned entities within the aggregate are synchronized to match the passed-in aggregate state; Spring Data JDBC may delete existing child rows and re-insert current ones.
- If the UPDATE affects no matching root row, the operation may fail because the target record was not found.

The decision point is **the state of the instance passed to save**, not simply whether a row with that ID exists in the database.

## 2. Entity State Detection: How does Spring Data recognize a new entity?

Spring Data provides three common strategies.

| Strategy | Rule |
| --- | --- |
| Inspect @Id | Default: null ID or 0 for primitive types marks the entity as new. |
| Inspect @Version | If a version property exists, null or 0 for primitive types indicates a new entity; any other value indicates an existing entity. |
| Implement Persistable | Spring Data calls isNew() provided by the entity. |

If there is no @Version property, Spring Data falls back to inspecting the ID. If the entity implements Persistable, isNew() becomes the authoritative source of newness.

### 2.1. Default @Id inspection

Example:

~~~java
@Table("products")
public record Product(
        @Id Long id,
        String name,
        BigDecimal price
) {
}
~~~

When creating a new product:

~~~java
Product product = new Product(
        null,
        "Mechanical Keyboard",
        new BigDecimal("120.00")
);

Product saved = repository.save(product);
~~~

A null ID signals a new aggregate. Spring Data JDBC generates an INSERT.

When reloaded:

~~~java
Product loaded = repository.findById(saved.id())
        .orElseThrow();
~~~

The ID now holds a value, so the aggregate is considered existing. Saving this instance follows the UPDATE branch.

### 2.2. Wrapper vs. primitive types

With a wrapper ID type:

~~~java
@Id
private Long id;
~~~

A null value represents an unassigned ID.

With a primitive ID type:

~~~java
@Id
private long id;
~~~

The value 0 is used to detect a new entity. If your application has custom ID rules where 0 is a valid ID, this default detection strategy may not fit.

In many models using generated keys, Long represents the unassigned state more cleanly than long.

### 2.3. When @Version is present

Example:

~~~java
@Table("products")
public record Product(
        @Id UUID id,
        String name,
        @Version Long version
) {
}
~~~

When @Version is present, Spring Data prioritizes checking version to determine whether the entity is new. A null version (or 0 for primitive types) indicates a new aggregate, even when the ID has already been assigned—such as an application-generated UUID.

After a successful save, version is updated so the instance is no longer considered new.

@Version also enables optimistic locking. Only add version when the application needs concurrent update protection or accepts those semantics; do not treat it merely as an inert technical flag.

## 3. Why might save choose the wrong operation?

### 3.1. Pre-assigned ID without marking the entity as new

For example, the application generates a UUID:

~~~java
Product product = new Product(
        UUID.randomUUID(),
        "Keyboard",
        null
);
~~~

If the entity relies only on default @Id checking, a non-null ID causes Spring Data to treat the instance as existing. save may execute an UPDATE even though no row exists in the database.

This can result in an error indicating the update affected zero rows, commonly represented by IncorrectUpdateSemanticsDataAccessException.

Solutions:

- Use @Version if the aggregate needs optimistic locking and null version indicates a new entity.
- Implement Persistable to define isNew() explicitly.
- Use JdbcAggregateTemplate.insert() when the caller knows for certain it is creating a new aggregate.
- Generate the ID inside a BeforeConvertCallback if the aggregate starts with a null ID and the callback assigns the ID after the new/existing decision has already been made.

Do not assume that generating a UUID on the Java side lets Spring Data automatically infer that an INSERT is needed.

### 3.2. Existing entity with null ID or isNew still returning true

If an aggregate already exists in the database, but the instance passed to save has a null ID, Spring Data may choose INSERT.

This can cause:

- Primary key or unique constraint violations.
- Duplicate records if a fresh ID is generated.
- Unintended creation of a new aggregate.
- Child data being inserted again under a new aggregate.

Check mappings and object construction. When updating, preserve the aggregate root ID from the prior load or supply the exact ID of the target record.

### 3.3. Persistable.isNew() always returns true

If an entity implements Persistable yet isNew() never flips to false after the initial insert, every subsequent save call will keep taking the INSERT branch.

This typically produces a duplicate key or unique constraint violation.

Conversely, if isNew() always returns false, the first save will run UPDATE and fail to find a matching row.

### 3.4. Accidentally using JPA annotations

Spring Data JDBC uses Spring Data's ID annotation:

~~~java
import org.springframework.data.annotation.Id;
~~~

JPA's jakarta.persistence.Id or GeneratedValue annotations do not replace Spring Data JDBC mappings.

For instance, an entity using JPA GeneratedValue without Spring Data @Id can prevent Spring Data JDBC from recognizing the primary key.

## 4. Using Persistable for Application-Assigned IDs

Persistable lets an entity determine its own newness via isNew().

Example mutable entity with an application-generated UUID:

~~~java
import java.util.UUID;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.domain.Persistable;
import org.springframework.data.relational.core.mapping.Table;

@Table("external_products")
public class ExternalProduct implements Persistable<UUID> {

    @Id
    private final UUID id;

    private String name;

    @Transient
    private boolean newEntity;

    protected ExternalProduct() {
        this.id = null;
        this.newEntity = false;
    }

    private ExternalProduct(
            UUID id,
            String name,
            boolean newEntity
    ) {
        this.id = id;
        this.name = name;
        this.newEntity = newEntity;
    }

    public static ExternalProduct create(
            UUID id,
            String name
    ) {
        return new ExternalProduct(id, name, true);
    }

    @Override
    public UUID getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    public void markPersisted() {
        this.newEntity = false;
    }

    public String getName() {
        return name;
    }

    public void rename(String name) {
        this.name = name;
    }
}
~~~

Because the ID is assigned before save, the newEntity flag distinguishes:

- A new aggregate that already has a UUID but has not been inserted yet.
- An already-saved aggregate with that same UUID.

### 4.1. Updating state after save

If isNew() remains true after INSERT, the next save will pick INSERT again. For mutable entities, an AfterSaveCallback can mark the instance as persisted:

~~~java
import org.springframework.data.relational.core.mapping.event.AfterSaveCallback;
import org.springframework.stereotype.Component;

@Component
public class ExternalProductSavedCallback
        implements AfterSaveCallback<ExternalProduct> {

    @Override
    public ExternalProduct onAfterSave(ExternalProduct aggregate) {
        aggregate.markPersisted();
        return aggregate;
    }
}
~~~

AfterSaveCallback runs after the aggregate is saved and can return either the same instance or a modified one.

The newEntity field is annotated with @Transient so it does not become a database column. If using property access, note that Persistable accessors might be detected as mapped properties; keep this metadata transient per mapping rules.

For immutable entities, the callback can return a new instance with isNew=false instead of mutating the existing object.

### 4.2. Testing Persistable

~~~java
@Test
void assignedUuidIsInsertedOnlyOnce() {
    UUID id = UUID.randomUUID();

    ExternalProduct created =
            ExternalProduct.create(id, "Keyboard");

    ExternalProduct saved = repository.save(created);

    assertEquals(id, saved.getId());
    assertFalse(saved.isNew());

    saved.rename("Mechanical Keyboard");

    ExternalProduct updated = repository.save(saved);

    assertEquals(id, updated.getId());
    assertEquals(
            "Mechanical Keyboard",
            updated.getName()
    );
}
~~~

This test verifies that an application-assigned ID does not cause Spring Data to confuse INSERT with UPDATE and that the new flag flips properly after save.

## 5. @Version Can Also Help Detect New Entities

If the aggregate already requires optimistic locking, a version property is a natural way for Spring Data to detect new vs. existing state.

~~~java
@Table("products")
public record Product(
        @Id UUID id,
        String name,
        @Version Long version
) {
}
~~~

Initialization:

~~~java
Product product = new Product(
        UUID.randomUUID(),
        "Keyboard",
        null
);

Product saved = repository.save(product);
~~~

A null version indicates a new aggregate. After INSERT, Spring Data updates the version in the returned instance. Subsequent saves take the UPDATE branch, and version is checked to detect stale writes.

Do not set a non-null version manually on a new aggregate if you intend to rely on this detection strategy.

## 6. Using JdbcAggregateTemplate.insert() and update() When State Is Known

JdbcAggregateTemplate provides explicit operations:

- save(): applies entity state detection like repository save().
- insert(): bypasses new/existing detection and always executes INSERT.
- update(): bypasses new/existing detection and always executes UPDATE.
- upsert(): inserts if the ID does not exist or updates if it does, when the dialect supports single-statement upsert.

Example:

~~~java
@Service
public class ProductPersistenceService {

    private final JdbcAggregateTemplate template;

    public ProductPersistenceService(
            JdbcAggregateTemplate template
    ) {
        this.template = template;
    }

    public Product create(Product product) {
        return template.insert(product);
    }

    public Product update(Product product) {
        return template.update(product);
    }
}
~~~

Use insert when the caller knows with certainty it is creating a new aggregate, even if an ID is already assigned. Use update when the caller knows the aggregate already exists.

Do not use insert merely to bypass entity state detection everywhere. If the row already exists, INSERT violates constraints. If update runs with a nonexistent ID, it may fail because no row is updated.

### 6.1. Is upsert always the best choice?

Upsert can be useful when the database dialect supports a single-step upsert statement. In Spring Data Relational 4.1.2, JdbcAggregateOperations provides upsert starting in version 4.1.

However:

- The aggregate root must have an ID.
- The dialect or DataAccessStrategy must support upsert.
- Upsert currently does not support optimistic locking.
- Database update/insert semantics can vary across vendors.

Do not replace save with upsert just to sidestep new-entity detection bugs. Choose based on business semantics and concurrency requirements.

## 7. How do generated keys work?

When the database has an auto-increment ID column, Spring Data JDBC can retrieve the generated key from the JDBC driver after INSERT and populate the ID on the returned aggregate.

Example entity:

~~~java
@Table("products")
public record Product(
        @Id Long id,
        String name,
        BigDecimal price
) {
}
~~~

H2 or PostgreSQL schema:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(12, 2) NOT NULL
);
~~~

MySQL schema:

~~~sql
CREATE TABLE products (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(12, 2) NOT NULL
);
~~~

Repository save:

~~~java
Product saved = repository.save(
        new Product(
                null,
                "Mechanical Keyboard",
                new BigDecimal("120.00")
        )
);

Long generatedId = saved.id();
~~~

Key prerequisites:

1. The ID field is annotated with Spring Data @Id.
2. The schema has a matching ID generation mechanism.
3. The database dialect is detected properly.
4. The JDBC driver supports returning generated keys in the manner Spring Data JDBC expects.
5. The application uses the instance returned by save.

### 7.1. Always capture the instance returned by save

Spring Data JDBC supports immutable aggregates. With records or immutable classes, the generated ID and version are reflected in the returned instance.

What not to do:

~~~java
Product product = new Product(
        null,
        "Keyboard",
        new BigDecimal("120.00")
);

repository.save(product);

// Do not assume the original immutable object received the ID.
Long id = product.id();
~~~

Correct approach:

~~~java
Product saved = repository.save(product);
Long id = saved.id();
~~~

For mutable entities, Spring Data may update the ID on the passed-in object, but capturing the return value ensures your code works properly for both mutable and immutable aggregates.

### 7.2. Database generates an ID, yet the returned object still has null

If INSERT succeeds yet the ID is missing from the returned object, check:

- Does the ID field have the right org.springframework.data.annotation.Id annotation?
- Is the column genuinely identity/auto-increment?
- Do table/column mappings match schema migrations?
- Do the driver and database version support generated keys?
- Did the resolver detect the right dialect?
- Is a hand-written SQL INSERT via @Query or JdbcTemplate being used instead of repository/template?
- Is a trigger or custom ID mechanism generating the ID in a way the driver does not return through the generated-key API?

Do not look solely at logs showing INSERT succeeded and assume the generated key was mapped.

## 8. Using Database Sequences with @Sequence

Some databases use sequences instead of auto-increment columns.

Spring Data JDBC supports @Sequence on the ID property if the dialect supports sequences.

Example:

~~~java
@Table("products")
public class Product {

    @Id
    @Sequence(
            sequence = "product_seq",
            schema = "public"
    )
    private Long id;

    private String name;
}
~~~

Create sequence:

~~~sql
CREATE SEQUENCE product_seq
    START WITH 1
    INCREMENT BY 1;
~~~

When saving, Spring Data JDBC runs a SELECT to fetch the next value from the sequence and then uses that value in the INSERT.

PostgreSQL example:

~~~sql
SELECT nextval('public.product_seq');
~~~

Then:

~~~sql
INSERT INTO products(id, name)
VALUES (:generatedId, :name);
~~~

Sequence support in Spring Data Relational 4.1.2 covers H2, HSQL, PostgreSQL, DB2, Oracle, and SQL Server. MySQL does not support sequences through this mechanism; MySQL typically uses AUTO_INCREMENT.

Fetching the sequence value and executing INSERT are two separate operations. Run them inside an enclosing transaction to maintain atomicity appropriate for your use case.

## 9. Using BeforeConvertCallback to Assign IDs in the Application

If the ID is generated in the application layer while the aggregate starts without an ID, you can use a BeforeConvertCallback to assign the ID before converting the object into a SQL plan.

Example:

~~~java
import java.util.UUID;

import org.springframework.data.relational.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class ProductIdCallback
        implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(Product product) {
        if (product.id() != null) {
            return product;
        }

        return new Product(
                UUID.randomUUID(),
                product.name(),
                product.price()
        );
    }
}
~~~

However, there is a crucial detail: Spring Data JDBC decides between INSERT and UPDATE **before** invoking BeforeConvertCallback.

Therefore:

- If the aggregate initially has a null ID, Spring has already detected it as new; the callback can assign a UUID and proceed with INSERT.
- If the aggregate already has a UUID before save is called, default ID inspection may treat it as existing.
- If you need to assign an ID before save while still performing INSERT, use @Version or Persistable to signal newness.

Do not use BeforeSaveCallback to generate IDs. By that stage, the INSERT/UPDATE decision and persistence plan have already been constructed. BeforeConvertCallback is the appropriate hook for ID assignment.

## 10. When to Use Generated ID, UUID, or Sequence?

| Strategy | Advantages | Things to watch out for |
| --- | --- | --- |
| Identity/auto-increment | Simple, database-managed | Requires generated key from driver; vendor-specific DDL |
| Sequence | ID available before INSERT, widely supported | Sequence must exist and dialect must support it |
| Application-generated UUID | ID available before insert, distributed-friendly | Must handle entity state detection |
| Database-generated UUID | Leverages database capabilities | Requires compatible mapping/driver and generated value verification |
| Externally assigned ID | Fits system integrations | Requires Persistable or explicit insert |

No single ID strategy fits every system. Consider distribution, ordering, index size, integration needs, and the target database.

## 11. Diagnosing save Running UPDATE Instead of INSERT

Common symptoms:

- Saving a new entity throws an error that the update affected zero rows.
- No INSERT appears in SQL logs.
- An UPDATE by ID runs even though no matching row exists.
- The entity uses a UUID assigned prior to save.
- The entity implements Persistable, yet isNew() returns false.

Verification checklist:

1. Check the ID value immediately before save.
2. Verify the ID annotation comes from the right Spring Data package.
3. Check whether the entity implements Persistable.
4. If @Version is present, check whether version is null/0 or already populated.
5. Enable SQL logging to see whether INSERT or UPDATE actually executes.
6. Check whether the row exists in the database.
7. If the ID is pre-assigned, choose Persistable, @Version, or template.insert() appropriately.
8. Do not call save for an operation known to require INSERT if entity state detection cannot accurately reflect its state.

Diagnostic logging example:

~~~java
log.debug(
        "Saving product: id={}, version={}, isNew={}",
        product.id(),
        product.version(),
        product.isNew()
);
~~~

If the entity does not implement Persistable or lacks a version property, omit isNew() and only log fields that exist.

## 12. Diagnosing save Running INSERT Instead of UPDATE

Symptoms:

- Saving an existing entity fails with duplicate primary key.
- Unique constraint violation.
- An aggregate has an ID yet has a null version.
- Persistable always returns true.
- The entity was reconstructed manually without retaining its ID or version.

Check:

1. Does the ID match the record being updated?
2. Is the version the current database version?
3. Does Persistable.isNew() return false for already-saved aggregates?
4. Did code accidentally construct a new object with an old ID but a new flag?
5. Was insert() called instead of update()/save()?
6. Did the aggregate root lose its ID while passing through a DTO or mapper?

Do not fix duplicate key errors by dropping constraints. Constraints protect uniqueness; fix the entity state and save flow instead.

## 13. Diagnosing Missing Generated Keys

| Symptom | Possible cause | What to check |
|---|---|---|
| ID is null after save | Original object is immutable and return value was ignored | Assign the result of save to a variable |
| INSERT omits ID, yet database generates none | Column lacks identity/auto-increment/default | Check DDL |
| Spring does not recognize ID property | Wrong JPA @Id used or missing Spring Data @Id | Check imports |
| Sequence does not run | Sequence does not exist or dialect unsupported | Check @Sequence and database |
| MySQL fails to read sequence | MySQL does not support sequences | Use AUTO_INCREMENT |
| Custom SQL insert returns no key | Hand-written SQL skips repository generated-key handling | Use KeyHolder or template |
| H2 test passes, production fails | Schema, dialect, or driver differences | Run integration tests on production database |
| ID returned, yet cannot reload | ID mapped with wrong type or schema/table mismatch | Check ID value and query directly |

### 13.1. Checking generated keys via JDBC metadata

You can inspect column metadata using DatabaseMetaData:

~~~java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata = connection.getMetaData();

    try (ResultSet columns = metadata.getColumns(
            null,
            null,
            "products",
            "id"
    )) {
        while (columns.next()) {
            System.out.println(
                    "Column: " + columns.getString("COLUMN_NAME")
            );
            System.out.println(
                    "Auto increment: "
                            + columns.getString("IS_AUTOINCREMENT")
            );
        }
    }
}
~~~

Driver-supplied metadata can vary across databases. Use this for diagnostics while also inspecting live DDL with database tooling.

### 13.2. When writing JDBC INSERTs manually

If bypassing repositories/templates and running INSERT via JdbcTemplate, request generated keys explicitly with KeyHolder:

~~~java
KeyHolder keyHolder = new GeneratedKeyHolder();

jdbc.update(connection -> {
    PreparedStatement statement = connection.prepareStatement(
            "INSERT INTO products(name, price) VALUES (?, ?)",
            Statement.RETURN_GENERATED_KEYS
    );

    statement.setString(1, "Keyboard");
    statement.setBigDecimal(2, new BigDecimal("120.00"));

    return statement;
}, keyHolder);

Number generatedKey = keyHolder.getKey();
~~~

This applies to manual JDBC paths. When using Spring Data JDBC repositories, let mappings and dialects handle generated keys via standard configuration.

## 14. Testing INSERT, UPDATE, and Generated Keys

A basic integration test should verify the full lifecycle:

~~~java
@SpringBootTest
class ProductPersistenceTest {

    @Autowired
    ProductRepository repository;

    @Test
    void insertsThenUpdatesProduct() {
        Product created = repository.save(
                new Product(
                        null,
                        "Keyboard",
                        new BigDecimal("100.00")
                )
        );

        assertNotNull(created.id());
        assertTrue(repository.existsById(created.id()));

        Product updated = repository.save(
                new Product(
                        created.id(),
                        "Mechanical Keyboard",
                        new BigDecimal("120.00")
                )
        );

        assertEquals(created.id(), updated.id());

        Product loaded = repository.findById(created.id())
                .orElseThrow();

        assertEquals("Mechanical Keyboard", loaded.name());
        assertEquals(
                new BigDecimal("120.00"),
                loaded.price()
        );
    }
}
~~~

This test requires the schema to be created by real migrations or matching DDL. When using records, always capture the object returned by save to retain the generated ID.

### 14.1. Testing application-assigned IDs

When using UUIDs:

1. Create the entity with a UUID before calling save.
2. Mark the entity as new using Persistable or @Version appropriately.
3. Save and confirm INSERT executes.
4. Confirm the ID remains unchanged.
5. Mark the entity as persisted.
6. Save again and confirm UPDATE executes instead of INSERT.
7. Verify the database contains only one row for that ID.

### 14.2. Testing sequences

For databases supporting sequences:

1. Create the sequence in migrations.
2. Map the ID with @Id and @Sequence.
3. Save a new aggregate.
4. Confirm the ID comes from the sequence.
5. Reload by ID.
6. Verify sequence permissions for the database user.
7. Confirm both sequence fetch and INSERT run inside an appropriate transaction.

### 14.3. Running on a real database

H2 works for fast feedback, but generated-key behavior must be verified against the production target database.

Use Testcontainers with the matching server and driver:

- PostgreSQL with the PostgreSQL JDBC driver.
- MySQL with MySQL Connector/J.
- H2 for smoke tests and basic mapping.

Pin the server version close to production. A test that only runs on H2 does not prove generated keys work properly on PostgreSQL or MySQL.

## 15. Common Misconceptions

**"save always runs INSERT."** No. Spring Data JDBC checks aggregate state and chooses either INSERT or UPDATE.

**"Having an ID means the entity definitely exists."** No. The ID might be assigned by the application before insert; new state must be represented accurately.

**"Null ID is always the only way to detect a new entity."** No. @Version and Persistable can also participate in entity state detection.

**"Use JPA @GeneratedValue for Spring Data JDBC ID generation."** No. Spring Data JDBC uses Spring Data's @Id and dialect-supported identity/sequence mechanisms.

**"If a UUID is pre-assigned, save automatically knows to INSERT."** No. With a non-null ID and no version/Persistable, the entity may be treated as existing by default.

**"BeforeConvertCallback can change UPDATE into INSERT."** No. The new/existing decision happens before the callback; the callback is meant for assigning IDs to entities already recognized as new.

**"BeforeSaveCallback is the place to generate IDs."** Not recommended. The persistence plan is already built by then; use BeforeConvertCallback for ID assignment.

**"Persistable.isNew() can always return true."** No. After insert it must transition to not-new, otherwise future saves will keep running INSERT.

**"Persistable.isNew() can always return false."** No. New entities will follow UPDATE and fail to find a matching row.

**"There is no need to keep the return value of save."** False for immutable aggregates. The generated ID and version live on the newly returned instance.

**"If the database inserts successfully, JDBC always returns the generated key."** Not every SQL path, driver, or schema behaves identically. Verify identity, dialect, driver, and generated-key support.

**"@Sequence works on every database."** No. Only sequence-supporting dialects support it; MySQL does not support sequences via this mechanism.

**"insert() is the same as save()."** No. insert() skips entity state detection and always runs INSERT. update() always runs UPDATE. Only use them when the caller knows the exact state.

**"upsert solves all save issues."** No. Upsert requires an assigned ID, depends on dialect support, and currently does not support optimistic locking.

**"If you can't retrieve the ID, just query MAX(id) yourself."** No. MAX(id) suffers from race conditions under concurrent inserts. Use proper generated keys or sequences.

## 16. Troubleshooting Workflow for save and Generated Keys

When save runs the wrong INSERT/UPDATE or fails to return an ID, check in order:

1. **Verify mapping:** the primary key field uses Spring Data @Id and table/column names match.
2. **Inspect entity state:** null/0 ID, null/0 version, or Persistable.isNew().
3. **Identify where the ID is assigned:** database identity, sequence, application UUID, or external system.
4. **Pick the right new-detection strategy:** default, @Version, or Persistable.
5. **Check callbacks:** if assigning IDs via a callback, use BeforeConvertCallback and remember the new/existing decision happens beforehand.
6. **Check schema:** identity/auto-increment/default/sequence exists with the right type.
7. **Check dialect/driver:** JDBC metadata recognizes the database and the driver supports generated keys.
8. **Inspect actual SQL:** confirm whether save emits INSERT or UPDATE.
9. **Capture returned instance:** take ID/version from the object returned by save.
10. **Verify in the database:** query directly by ID rather than inspecting only the Java object.
11. **Test insert then update:** confirm the same aggregate follows both branches properly.
12. **Run integration tests on target database:** pin server and JDBC driver versions close to production.

~~~mermaid
flowchart TD
    A["Call save(aggregate)"] --> B{"Is entity considered new?"}
    B -->|Yes| C["INSERT"]
    B -->|No| D["UPDATE"]
    C --> E{"Database generates ID?"}
    E -->|Yes| F["Read generated key and return saved instance"]
    E -->|No| G["Check app ID / sequence / callback"]
    D --> H{"Rows updated?"}
    H -->|Yes| I["Return saved instance"]
    H -->|No| J["Check ID, isNew, version, and row existence"]
    F --> K["Use returned instance"]
    G --> K
    I --> K
    J --> L["Fix entity state or mapping"]
~~~

## 17. Practice Exercises

Create a Product aggregate with id, name, price, and its corresponding repository.

### Exercise 1: Observe INSERT and UPDATE

1. Create a Product with a null ID.
2. Save it with SQL logging enabled.
3. Confirm an INSERT statement executes.
4. Read the ID from the returned instance.
5. Reload the aggregate.
6. Change the name and save.
7. Confirm an UPDATE statement executes.

### Exercise 2: Simulate save Choosing UPDATE Wrongly

1. Create a new Product with a pre-assigned UUID.
2. Do not implement Persistable or @Version.
3. Call save.
4. Observe Spring treating the entity as existing.
5. Confirm the update affects zero rows.
6. Retry with Persistable.isNew() returning true.

### Exercise 3: Verify Persistable State

1. Create an entity with a UUID and newEntity=true.
2. Implement Persistable.
3. Register an AfterSaveCallback to flip the flag to false.
4. Save the first time.
5. Rename and save a second time.
6. Confirm the first save runs INSERT and the second runs UPDATE.

### Exercise 4: Verify Generated Keys

1. Create a table with identity/auto-increment.
2. Map the ID with Spring Data @Id.
3. Save an entity with a null ID.
4. Confirm the ID is returned.
5. Reload by ID.
6. Test with an immutable record and confirm you must use the returned instance.

### Exercise 5: Verify Sequences

1. Create a sequence on PostgreSQL or H2.
2. Map @Id with @Sequence.
3. Save an aggregate.
4. Confirm the sequence value is fetched before INSERT.
5. Verify the ID and data after save.
6. Try on MySQL and explain why AUTO_INCREMENT must be used instead of @Sequence.

### Exercise 6: Test on Production Target Database

1. Run identity tests on H2.
2. Run the same tests on a PostgreSQL Testcontainer or MySQL Testcontainer.
3. Compare returned IDs and executed SQL.
4. Check the JDBC driver version.
5. Test migrating from an old schema to a new schema.
6. Write a regression test for any discovered bug.

## 18. Key Takeaways

- Spring Data JDBC chooses INSERT or UPDATE using entity state detection before generating SQL.
- By default, a null ID or primitive 0 indicates a new entity.
- When @Version is present, null or primitive 0 indicates a new entity; any other version indicates an existing entity.
- Implement Persistable to define isNew() explicitly when IDs are assigned by the application or an external system.
- Persistable must transition to not-new state after a successful save.
- @Id must be org.springframework.data.annotation.Id, not JPA @Id.
- BeforeConvertCallback is suitable for assigning IDs to aggregates already recognized as new; callbacks cannot alter the earlier INSERT/UPDATE decision.
- JdbcAggregateTemplate.insert() always runs INSERT; update() always runs UPDATE; save() uses entity state detection.
- upsert() requires a pre-assigned ID, depends on dialect support, and currently does not support optimistic locking.
- With identity/auto-increment, the database generates the key and Spring Data JDBC populates it on the returned instance.
- Always keep the instance returned by save, especially with records or immutable aggregates.
- @Sequence works only on dialects supporting sequences; MySQL uses AUTO_INCREMENT.
- When failing to retrieve generated keys, inspect @Id mapping, DDL, dialect, JDBC driver, and the actual SQL path.
- Test both INSERT and UPDATE on the target production database, not only on H2.

**save chooses INSERT or UPDATE accurately only when entity state reflects the aggregate's true lifecycle.** Inspect ID, version, and isNew before altering schemas. For generated keys, confirm the database genuinely generates the ID and always use the instance returned by save. Following this approach avoids duplicate inserts, zero-row updates, and missing generated keys when working with Spring Data JDBC.

## References

- [Spring Data Relational 4.1.2 — Persisting Entities and ID Generation](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html)
- [Spring Data Commons 4.1.2 — Entity State Detection](https://docs.spring.io/spring-data/relational/reference/data-commons/is-new-state-detection.html)
- [Spring Data Relational 4.1.2 — Sequence Support](https://docs.spring.io/spring-data/relational/reference/jdbc/sequences.html)
- [Spring Data Relational 4.1.2 — JdbcAggregateOperations API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/JdbcAggregateOperations.html)
- [Spring Data Commons 4.1.2 — Persistable API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/domain/Persistable.html)
- [Spring Data Relational 4.1.2 — AfterSaveCallback API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/event/AfterSaveCallback.html)
