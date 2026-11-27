# Avoiding Projections or Partial-Column Aggregates as Input to `save`

In Spring Data JDBC, **projections and DTOs generally serve partial data reads**, whereas **`repository.save(aggregate)`** uses an aggregate object to synchronize stored state. Those two purposes are distinct.

A projection containing only product ID, name, and price may suffice for rendering a list. However, if you take those three values, construct a partial Product object, and call save, the application can accidentally overwrite omitted properties or wipe out owned child entities inside the aggregate.

Spring Data JDBC does not retain a prior snapshot to infer “update only the name field.” When saving an existing aggregate, the framework treats the passed-in object as the target state to persist. For owned child entities, the update mechanism can even delete existing child rows and re-insert rows according to the collection on the passed aggregate.

Therefore, distinguish clearly between:

- **Read projection/DTO:** fetching a slice of data for display, reports, or API responses.
- **Full aggregate:** used to execute domain changes and save via the repository.
- **Partial updates:** using read-modify-save with the full aggregate, an intentional SQL update statement, or a dedicated reduced aggregate-root mapping.

This lesson explains the risks of passing partial-column data into save, how to choose safe update patterns, and what responsibilities you must protect manually when using custom SQL.

## 1. Projections and Persistence Aggregates Serve Different Purposes

A projection is a result type exposing only the properties a read use case needs. For example, a list screen only needs product ID, name, and price:

~~~java
public interface ProductSummary {
    Long getId();
    String getName();
    BigDecimal getPrice();
}
~~~

The repository can declare a query method returning the projection:

~~~java
public interface ProductRepository
        extends CrudRepository<Product, Long> {

    List<ProductSummary> findByStatus(String status);
}
~~~

Read use case:

~~~java
List<ProductSummary> products =
        productRepository.findByStatus("ACTIVE");
~~~

Here, the application only needs to display three fields. The projection is not a complete aggregate and should not be treated as a persistence object to save back.

An aggregate root may carry many more properties:

~~~java
@Table("products")
public class Product {

    @Id
    private Long id;

    private String name;
    private BigDecimal price;
    private String status;
    private String description;
    private boolean active;

    @Version
    private Long version;

    @MappedCollection(
            idColumn = "product_id",
            keyColumn = "attribute_position"
    )
    private List<ProductAttribute> attributes = new ArrayList<>();

    // Constructors, getters, and domain methods
}
~~~

The ProductSummary projection omits status, description, active, version, and attributes. That is completely normal for a read model.

Trouble begins when the application converts projection data into a savable instance without restoring the missing state.

## 2. Why Is Saving an Incomplete Aggregate Dangerous?

Spring Data JDBC does not maintain a persistence context to track individual dirty properties like some ORMs. The framework cannot tell whether a missing property in an object means:

- The user wants to clear the value.
- A projection omitted that property.
- A mapper forgot to populate the property.
- A constructor fell back to a default value.
- A collection was never loaded.
- The data genuinely holds null or empty.

When save is called, the state of the passed aggregate becomes the basis for persistence.

Spring Data Relational documentation explains that for an existing aggregate root, Spring Data JDBC deletes referenced entities inside the aggregate, updates the root, and re-inserts referenced entities according to the current state. Because the framework does not know the aggregate's prior state, it synchronizes the database to match the passed-in object.

This creates two categories of risk.

### 2.1. Scalar Properties Overwritten with Unintended Values

Suppose the table is:

~~~sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    price NUMERIC(12, 2) NOT NULL,
    status VARCHAR(30) NOT NULL,
    description VARCHAR(1000),
    active BOOLEAN NOT NULL,
    version BIGINT NOT NULL
);
~~~

Existing data:

~~~text
id   name       price     status   description         active   version
---  ---------  --------  -------  ------------------  -------  -------
10   Keyboard   120.00    ACTIVE   Mechanical switch   true     4
~~~

The projection has only:

~~~java
public record ProductSummary(
        Long id,
        String name,
        BigDecimal price
) {
}
~~~

If a mapper constructs a partial aggregate:

~~~java
Product partial = new Product(
        summary.id(),
        summary.name(),
        summary.price(),
        null,       // status is not in the projection
        null,       // description is not in the projection
        false,      // active receives primitive default
        null,       // version is not in the projection
        List.of()   // attributes were not loaded
);
~~~

then those null, false, and empty collection values may be treated as the intended state to persist.

Depending on mapping and schema, the outcome can be:

- status set to NULL or failing a NOT NULL constraint.
- description erased.
- active flipped to false even though it was true.
- missing version breaking optimistic locking or state detection.
- attributes collection synchronized as empty, deleting existing child rows.

This is not a flaw in projections. The projection did its job by reading minimal data. The mistake lies in treating partial read data as complete aggregate state for writes.

### 2.2. Owned Child Entities Can Be Deleted

The risk to collections is even more severe.

Suppose a product has three attributes:

~~~text
Product 10
  attributes:
    COLOR = BLACK
    LAYOUT = US
    SWITCH = RED
~~~

A projection reads only id and name. When a mapper instantiates a new aggregate without the collection, the constructor may leave attributes as List.of().

If save is called with an existing aggregate, Spring Data JDBC can synchronize the owned collection to that empty state. Existing child rows can be deleted.

~~~text
Database before save:
  product_attributes
    product_id = 10, COLOR = BLACK
    product_id = 10, LAYOUT = US
    product_id = 10, SWITCH = RED

Aggregate built from projection:
  id = 10
  name = Keyboard
  attributes = []

After save:
  product_attributes for product 10 no longer has those rows
~~~

Therefore, **never assume that a collection omitted from a projection means the collection remains untouched**. For aggregate persistence, an empty collection is a meaningful state and can be persisted to the database.

## 3. Distinguishing Projections, DTOs, and Reduced Aggregate Roots

The following types may look similar in Java, yet have distinct roles.

| Type | Purpose | Pass directly to save? |
| --- | --- | --- |
| Projection interface | Read a subset of properties via accessors | No |
| Query result DTO/record | Return data to API, report, or screen | No |
| Command DTO | Carry change intent from client to service | No |
| Full aggregate root | Represent domain state managed by repository | Yes |
| Reduced aggregate-root mapping | Intentionally map a subset of root columns in the same table for narrow use cases | Possible, but requires understanding limits |

### 3.1. Projection Interface

Example:

~~~java
public interface ProductSummary {
    Long getId();
    String getName();
}
~~~

It describes values to read. There is no contract stating the projection carries every property or collection of the aggregate.

### 3.2. DTO/Record

Example:

~~~java
public record ProductDetailsDto(
        Long id,
        String name,
        BigDecimal price,
        String status
) {
}
~~~

A DTO can serve as a response or intermediate data structure. Having fields that overlap with an entity does not make it an aggregate.

### 3.3. Command DTO

Example rename request:

~~~java
public record RenameProductRequest(String newName) {
}
~~~

A Command DTO expresses **intent**: rename the product. It does not need to carry the full product and should never be saved directly to the repository.

The service uses the command to mutate the full aggregate:

~~~java
@Transactional
public Product renameProduct(
        Long productId,
        RenameProductRequest request
) {
    Product product = productRepository.findById(productId)
            .orElseThrow();

    product.rename(request.newName());

    return productRepository.save(product);
}
~~~

This is safe and straightforward: load the full aggregate, apply domain behavior, then save.

### 3.4. Reduced Aggregate-Root Mapping Is a Special Case

Spring Data JDBC can also map another class to the same table containing only a subset of aggregate root properties. This is an intentional technique for partial root updates in suitable use cases.

For example, the products table has id, name, price, status, description, active, and version columns. A reduced mapping class might include only id, name, and version:

~~~java
@Table("products")
public class ProductNameView {

    @Id
    private Long id;

    private String name;

    @Version
    private Long version;

    protected ProductNameView() {
    }

    public ProductNameView(Long id, String name, Long version) {
        this.id = id;
        this.name = name;
        this.version = version;
    }

    // Getters
}
~~~

Separate repository:

~~~java
public interface ProductNameViewRepository
        extends CrudRepository<ProductNameView, Long> {
}
~~~

This is neither an interface projection nor a DTO. It is an intentional persistence mapping to the same table, acting as a reduced view of the aggregate root.

When saving this object, Spring Data JDBC knows only about the properties mapped by this class. Other root columns outside this mapping can remain preserved in the database. However, this technique should be applied selectively only to **aggregate roots**; never generalize it as a safe rule for child entities inside an aggregate.

Spring's article on partial updates explains this approach and emphasizes the limitation for entities inside an aggregate: they are deleted and re-created; columns missing from a child entity's reduced view can revert to default values.

## 4. The Safest Approach: Read-Modify-Save with the Full Aggregate

For typical domain changes, load the aggregate through the repository before modifying it.

Example:

~~~java
@Table("products")
public class Product {

    @Id
    private Long id;

    private String name;
    private BigDecimal price;
    private String status;
    private String description;
    private boolean active;

    @Version
    private Long version;

    @MappedCollection(
            idColumn = "product_id",
            keyColumn = "attribute_position"
    )
    private List<ProductAttribute> attributes = new ArrayList<>();

    protected Product() {
    }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException(
                    "Product name is required"
            );
        }
        this.name = newName;
    }

    public void changePrice(BigDecimal newPrice) {
        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException(
                    "Price must be non-negative"
            );
        }
        this.price = newPrice;
    }

    public void deactivate() {
        this.active = false;
    }
}
~~~

Service:

~~~java
@Transactional
public Product changePrice(Long id, BigDecimal newPrice) {
    Product product = productRepository.findById(id)
            .orElseThrow();

    product.changePrice(newPrice);

    return productRepository.save(product);
}
~~~

Data flow:

~~~text
Client sends command
       |
       v
Service receives productId + changed data
       |
       v
Repository loads full aggregate
       |
       v
Aggregate executes domain method
       |
       v
Repository.save(aggregate)
       |
       v
Database synchronizes aggregate state
~~~

This preserves loaded properties and collections while giving the aggregate a chance to enforce invariants before persisting.

### 4.1. Why Not Construct a New Entity Only from the Request?

Unsafe:

~~~java
@Transactional
public Product changePrice(
        Long id,
        BigDecimal newPrice
) {
    Product partial = new Product();
    partial.setId(id);
    partial.setPrice(newPrice);

    return productRepository.save(partial);
}
~~~

This object holds only ID and the new price. Other properties may be null/default and collections empty. Save does not automatically understand “update only price.”

Instead:

~~~java
@Transactional
public Product changePrice(
        Long id,
        BigDecimal newPrice
) {
    Product product = productRepository.findById(id)
            .orElseThrow();

    product.changePrice(newPrice);

    return productRepository.save(product);
}
~~~

The difference is that the second aggregate is restored from the database before mutation.

### 4.2. Use Projections to Read, Aggregates to Write

A service can use projections on the read path and full aggregates on the write path:

~~~java
public interface ProductRepository
        extends CrudRepository<Product, Long> {

    List<ProductSummary> findByStatus(String status);
}
~~~

Read:

~~~java
public List<ProductSummary> listActiveProducts() {
    return productRepository.findByStatus("ACTIVE");
}
~~~

Write:

~~~java
@Transactional
public Product rename(Long id, String newName) {
    Product product = productRepository.findById(id)
            .orElseThrow();

    product.rename(newName);

    return productRepository.save(product);
}
~~~

This establishes a clean separation of duties: projections serve read queries, aggregate roots serve domain mutations and persistence.

## 5. When Might a Reduced Aggregate-Root Mapping Fit?

Not every partial update strictly requires loading the entire aggregate if the use case only updates a few root columns and can be cleanly isolated.

For instance, an administrative task only renames a product. The domain can define a dedicated mapping against the same table:

~~~java
@Table("products")
public record ProductNameRecord(
        @Id Long id,
        String name,
        @Version Long version
) {
}
~~~

Repository:

~~~java
public interface ProductNameRecordRepository
        extends CrudRepository<ProductNameRecord, Long> {
}
~~~

Service:

~~~java
@Transactional
public ProductNameRecord renameUsingReducedRoot(
        Long id,
        String newName
) {
    ProductNameRecord current =
            productNameRecordRepository.findById(id)
                    .orElseThrow();

    ProductNameRecord updated = new ProductNameRecord(
            current.id(),
            newName,
            current.version()
    );

    return productNameRecordRepository.save(updated);
}
~~~

This can help when:

- Only aggregate root columns are updated.
- Child collections are not needed for the use case.
- The version column is handled properly to prevent overwriting concurrent changes.
- The reduced mapping is treated as a dedicated persistence model rather than confused with the full aggregate.
- Tests verify that columns omitted from the reduced mapping remain intact.

**This is an advanced technique, not a default replacement for the aggregate root.** If a use case touches business rules tied to other properties or child collections, load the full aggregate.

### 5.1. Limitation: Apply Intentionally Only to Aggregate Roots

Suppose the Product aggregate has an attributes collection. The reduced root mapping does not declare that collection:

~~~text
Full Product aggregate:
  id
  name
  price
  status
  version
  attributes[]

Reduced root mapping:
  id
  name
  version
~~~

When saving the reduced root mapping, Spring Data JDBC has no metadata treating attributes as part of this mapping; child rows are not deleted merely because the reduced class omits that collection.

However, if you create a reduced mapping for a **child entity**:

~~~java
@Table("product_attributes")
public record ProductAttributeView(
        Long productId,
        String key
) {
}
~~~

and use it to partially save a child entity inside an aggregate, aggregate persistence behavior can delete and re-create child entities. Columns omitted from the reduced view may revert to defaults or unintended values.

Therefore, never use a reduced child entity as a general partial-update solution.

### 5.2. Protecting Root and Child with Foreign Keys

When mapping a reduced root to the same table as the full aggregate, the schema should still protect child table relationships.

Example:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    price NUMERIC(12, 2) NOT NULL,
    status VARCHAR(30) NOT NULL,
    version BIGINT NOT NULL
);

CREATE TABLE product_attributes (
    product_id BIGINT NOT NULL REFERENCES products(id),
    attribute_position INTEGER NOT NULL,
    attribute_key VARCHAR(100) NOT NULL,
    attribute_value VARCHAR(500) NOT NULL,
    PRIMARY KEY (product_id, attribute_position)
);
~~~

Foreign keys prevent deleting the root while child rows still exist unless an intentional cascade policy applies. Exercise care when multiple repositories map the same table; deletes from a reduced repository still affect the entire root and must obey schema/domain rules.

## 6. Updating a Single Column via Intentional SQL

If the goal is to update a couple of columns without running full aggregate persistence, you can use a custom SQL statement.

Repository example:

~~~java
import org.springframework.data.jdbc.repository.query.Modifying;
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository
        extends CrudRepository<Product, Long> {

    @Modifying
    @Query("""
            UPDATE products
               SET name = :name,
                   version = version + 1
             WHERE id = :id
               AND version = :version
            """)
    int renameIfVersionMatches(
            @Param("id") Long id,
            @Param("name") String name,
            @Param("version") Long version
    );
}
~~~

Service:

~~~java
@Transactional
public void renameWithDirectUpdate(
        Long id,
        String newName
) {
    Product current = productRepository.findById(id)
            .orElseThrow();

    int updated = productRepository.renameIfVersionMatches(
            id,
            newName,
            current.getVersion()
    );

    if (updated != 1) {
        throw new OptimisticLockingFailureException(
                "Product was changed by another transaction"
        );
    }
}
~~~

The example checks version in WHERE and increments version in the same statement. This prevents a request carrying stale data from overwriting a newer update.

However, direct SQL **bypasses part of Spring Data JDBC's persistence machinery**. The application must uphold the corresponding behaviors itself.

### 6.1. Responsibilities When Using Direct SQL

| Standard mechanism | Considerations with custom SQL |
| --- | --- |
| Optimistic locking | Check version in WHERE and increment version properly. |
| Auditing | Update columns such as updated_at, updated_by manually if needed. |
| Domain behavior | Design/invoke service logic to enforce invariants before writing. |
| Entity callbacks | Determine which callbacks no longer run and whether replacements are needed. |
| Events | If the application publishes events on save, direct updates need an explicit publishing mechanism. |
| Transaction | Define transaction boundaries covering SQL and related operations. |
| Validation | Validate input data and database constraints. |

If an UPDATE SQL statement fails to increment version while other entities use `@Version`, a stale object may miss the direct update. That weakens optimistic locking.

### 6.2. When to Use a Custom Repository?

If a partial update is complex, spans multiple SQL statements, or targets specific child tables, a custom repository implementation can be cleaner than a long `@Query` method.

For example, a custom repository can use NamedParameterJdbcOperations to:

1. Validate the data to be updated.
2. Execute a version-guarded UPDATE statement.
3. Verify the affected row count.
4. Update secondary tables if business rules require.
5. Throw an optimistic locking exception if zero rows were updated.

This is flexible, though it carries the responsibility of managing rules that default repository persistence ordinarily handles.

## 7. Do Not Confuse Partial Updates with Insert/Update/Upsert

Persistence APIs have distinct meanings:

| API | Meaning |
| --- | --- |
| CrudRepository.save(aggregate) | Determines whether aggregate is new or existing, then inserts/updates the aggregate. |
| JdbcAggregateTemplate.insert(aggregate) | Assumes aggregate is new and executes insert. |
| JdbcAggregateTemplate.update(aggregate) | Assumes aggregate exists and executes update. |
| JdbcAggregateTemplate.upsert(aggregate) | Uses native upsert if supported by dialect and aggregate has an ID. |
| `@Modifying` `@Query` | Executes custom application-defined SQL update/delete. |

JdbcAggregateTemplate.update does not mean “update only changed properties.” It remains an aggregate update operation governed by persistence mapping. Likewise, save is not an automatic PATCH command that changes only non-null fields.

Native upsert does not solve partial aggregates either. It chooses insert vs. update by key; it does not treat omitted properties on an object as “unchanged.”

## 8. Scenarios Prone to Data Loss

### 8.1. Mapping a DTO Directly to an Entity

Unsafe:

~~~java
Product product = mapper.toProduct(updateRequest);
productRepository.save(product);
~~~

If updateRequest carries only a few fields, the mapper may build an object with the remaining properties set to null/default.

Safer:

~~~java
Product product = productRepository.findById(updateRequest.id())
        .orElseThrow();

product.changePrice(updateRequest.price());

productRepository.save(product);
~~~

### 8.2. Collection Omitted from Request

Suppose a product rename request has no attributes field. If a mapper constructs a new aggregate with an empty attributes collection, save may wipe the existing collection.

For update APIs, distinguish:

- Collection omitted: do not change the collection.
- Empty collection sent: clear the collection.
- Populated collection sent: update per API contract.

Never use a DTO missing fields as a persistence aggregate object.

### 8.3. Primitives Reset to Defaults

If a DTO lacks an active field and a mapper builds an entity with primitive boolean active, its value may become false. Save could write false even though the product was active.

For optional request fields, wrappers like Boolean let you detect null, though null still requires interpretation per contract. It does not automatically mean “keep old value.”

### 8.4. Skipping Optimistic Locking

If a mapper omits version and builds an aggregate with null or default version, save may fail or fail to guard concurrent updates as intended.

Do not strip version merely because a response DTO does not display it. Version is persistence metadata, not necessarily a public API field.

### 8.5. Reduced Mapping for Child Entities

This is hazardous because Spring Data JDBC can delete and re-create child entities on aggregate save. If a child mapping omits columns, missing values may revert to defaults.

To change a property on an owned child entity, load the full aggregate, mutate through the root, and save; or consider controlled custom SQL and re-evaluate aggregate boundaries if children need independent updates.

## 9. Designing Clear Read DTOs and Write DTOs

Applications commonly have three distinct data models:

~~~text
Database
   |
   v
Aggregate root (domain + persistence)
   |
   +----> Projection / Read DTO ----> API response / UI
   |
   <---- Command DTO --------------- API request / use case
~~~

### 9.1. Read DTO

Used for presenting data:

~~~java
public record ProductListItem(
        Long id,
        String name,
        BigDecimal price
) {
}
~~~

Read DTOs can omit many properties because screens do not need them.

### 9.2. Command DTO

Used to express intent:

~~~java
public record ChangeProductPriceCommand(
        BigDecimal newPrice
) {
}
~~~

Command DTOs carry only the values required for the use case. The service decides how to apply them to the aggregate.

### 9.3. Aggregate Root

Used to execute domain behavior and persistence:

~~~java
public void changePrice(BigDecimal newPrice) {
    if (newPrice == null || newPrice.signum() < 0) {
        throw new IllegalArgumentException("Invalid price");
    }

    this.price = newPrice;
}
~~~

Do not expose the entire aggregate in a response DTO, and do not use a response DTO as an entity for save. Keeping all three models separate prevents responsibility confusion.

## 10. Partial Multi-Field Updates via Commands

A command can update several properties:

~~~java
public record UpdateProductCommand(
        String name,
        BigDecimal price,
        Boolean active
) {
}
~~~

Service:

~~~java
@Transactional
public Product updateProduct(
        Long id,
        UpdateProductCommand command
) {
    Product product = productRepository.findById(id)
            .orElseThrow();

    if (command.name() != null) {
        product.rename(command.name());
    }

    if (command.price() != null) {
        product.changePrice(command.price());
    }

    if (command.active() != null) {
        product.setActive(command.active());
    }

    return productRepository.save(product);
}
~~~

This implements a “null means unchanged” contract for the three command fields. If an API must allow clearing a value by sending null, add an explicit presence representation, since null is already used here to mean “do not update.”

For PATCH APIs, you can use wrapper/presence types, JSON Merge Patch, field masks, or a command structure explicitly representing three states:

- Field omitted: keep existing value.
- Value provided: update.
- Explicit null provided: clear value if the domain permits.

Once intent is clear, the service still loads the full aggregate and applies controlled changes.

## 11. Notes on Projections and Repository Methods

Spring Data supports projections in query methods to return partial properties. Example:

~~~java
public interface ProductRepository
        extends CrudRepository<Product, Long> {

    List<ProductSummary> findByStatus(String status);
}
~~~

Projections can be interface-based or class-based DTOs depending on declaration and store module support. Remember:

- A projection is a query result type.
- Projections do not alter the original aggregate mapping.
- Projections do not automatically become persistable objects.
- Do not override a base repository method like findById with a projection return type expecting Spring Data to turn it into a different query method; base methods may be invoked under their original contract without applying projection as expected.
- With custom queries, ensure returned columns align with the declared projection/DTO.

If your goal is reading fewer columns, projections are a good choice. If your goal is updating fewer columns, pick read-modify-save, intentional reduced root mapping, or custom update SQL. Do not mix both use cases into a single object type.

## 12. Checking Impact When Saving Aggregates

When investigating data loss after save, check:

1. Was the object passed to the repository a full aggregate or built from a projection/DTO?
2. Which scalar fields were never loaded and carry null/default values?
3. Which collections were never loaded yet initialized as empty collections?
4. Were any child entities deleted and re-created on save?
5. Does another reduced mapping point to the same root or child table?
6. Is version read and updated properly?
7. Does custom SQL bypass auditing, callbacks, or domain behavior?
8. Does the database enforce foreign keys and constraints protecting critical data?
9. What actual SQL statements are emitted?
10. Are concurrent requests overwriting newer state with stale state?

Enable SQL logging in development or use a JDBC tracing tool to inspect actual statements. Never infer from a Java method named save that the framework updates only one column.

## 13. Common Mistakes

**“The projection has an ID, so it can be saved like an entity.”** Incorrect. An ID is only part of identity; a projection may lack properties and collections needed to represent aggregate state.

**“Fields absent from a DTO will be preserved on save.”** Incorrect if a mapper constructs a full aggregate with null/default values for those fields. Spring Data JDBC does not automatically treat missing fields as “unchanged.”

**“Collections omitted from a projection will be kept intact.”** Incorrect if you construct an aggregate with an empty collection and call save; owned collection state may be synchronized to empty.

**“Save only updates non-null fields.”** Incorrect. Save is not PATCH. Null may be persisted as a target value if mapping and schema permit.

**“Using Optional in a projection and mapping to an entity is enough.”** Not automatically. Optional expresses nullable values in a read model, not the full presence semantics of an update command.

**“Reduced aggregate roots and projections are the same.”** No. A reduced aggregate-root mapping is an intentional persistence type mapped to the same table; a projection is a read result type. Reduced roots have limits and must be managed separately.

**“Reduced views can be used for child entities.”** Avoid this. Child entities inside an aggregate may be deleted and re-created on save; columns omitted from mapping can revert to defaults.

**“Direct UPDATE doesn't need version.”** Incorrect if the aggregate uses optimistic locking. Custom SQL must guard version and check affected row counts manually.

**“Direct UPDATE still runs callbacks and auditing automatically.”** Do not assume so. Custom SQL bypasses part of normal persistence machinery; handle those responsibilities explicitly.

**“Testing the happy path is enough.”** Insufficient. Verify that untouched columns and child collections remain intact after the operation.

## 14. Workflow for Choosing the Right Update Strategy

When a use case modifies only a few fields, follow these steps:

1. **Identify the input data:** projection, response DTO, or command DTO?
2. **Identify the write target:** full aggregate root or intentional reduced mapping?
3. **If domain behavior is needed:** load the full aggregate, call domain methods, then save.
4. **If updating a single independent column:** consider an SQL update/custom repository and manage version, auditing, and callbacks.
5. **If using a reduced aggregate-root mapping:** restrict to appropriate root fields, isolate the repository/mapping cleanly, and check version.
6. **Do not use reduced child entities:** avoid losing unmapped columns when children are deleted/re-created.
7. **Check collections:** ensure “not loaded” never turns into “empty collection” during save.
8. **Check transactions and concurrency:** use optimistic locking or suitable concurrency control.
9. **Inspect actual SQL:** confirm columns and child rows outside the update scope stay intact.
10. **Check schema:** use constraints/foreign keys to guard against unintended child data loss.

~~~mermaid
flowchart TD
    A["Have partial data from projection/DTO"] --> B{"Is the goal reading?"}
    B -->|Yes| C["Use projection / read DTO"]
    B -->|No, need to write| D{"Need domain behavior or multi-part aggregate changes?"}
    D -->|Yes| E["Load full aggregate"]
    E --> F["Apply command via domain method"]
    F --> G["repository.save(aggregate)"]
    D -->|No| H{"Controlled update of root fields only?"}
    H -->|Yes| I["Reduced aggregate-root mapping or direct SQL"]
    H -->|No| J["Design custom repository / review boundaries"]
    I --> K["Protect version, auditing, callbacks, constraints, and transactions"]
    J --> K
    G --> L["Verify data and collections"]
    K --> L
~~~

## 15. Practice Exercises

Create a `products` table with `id`, `name`, `price`, `status`, `description`, `active`, and `version` columns. Also create a `product_attributes` table with a foreign key referencing `products`.

### Exercise 1: Reading with a Projection

1. Declare `ProductSummary` with only `id`, `name`, and `price`.
2. Write `findByStatus` returning `List<ProductSummary>`.
3. Use the projection to render a product list.
4. Confirm the read use case does not load the `attributes` collection.

### Exercise 2: Attempting `save` from a Partially Populated Aggregate

1. Read a projection.
2. Build a persistence aggregate object where fields absent from the projection receive null/default values.
3. Call `save` on isolated test data.
4. Observe scalar columns and child collections.
5. Explain why `save` treats default values as state to persist.

Never run destructive experiments against production data.

### Exercise 3: Read-Modify-Save

1. Load the full aggregate using `findById`.
2. Rename via a domain method.
3. Save the aggregate.
4. Reload and confirm other columns and child collections remain intact.

### Exercise 4: Reduced Aggregate-Root Mapping

1. Create a reduced persistence class mapping the `products` table.
2. Declare only ID, name, and version.
3. Use a separate repository to rename the product.
4. Verify `price`, `status`, `description`, `active`, and `product_attributes` remain intact.
5. Try deleting the root via the reduced repository in a test environment and observe the FK protecting the child table.

### Exercise 5: Direct SQL Update

1. Write a `@Modifying` `@Query` method updating only the product name.
2. Add `WHERE id = :id AND version = :version`.
3. Increment version in the same statement.
4. Check the updated row count.
5. Retry with a stale version and confirm the update is rejected.
6. Add auditing column updates if the schema requires them.

### Exercise 6: Distinguishing PATCH Cases

Create requests covering three cases:

- `description` omitted.
- `description` provided as a new string.
- `description: null`.

Design a command/DTO so the service clearly distinguishes keeping, replacing, and clearing the value. Then load the full aggregate and apply the corresponding mutation.

## 16. Key Takeaways

- Projections and DTOs are usually read models; never use them as aggregate persistence objects.
- `repository.save` persists the passed aggregate state; it does not treat fields omitted from a DTO as “keep unchanged.”
- Aggregates missing scalar fields may carry null/defaults and overwrite stored data.
- Owned collections that were never loaded yet initialized as empty can be synchronized to empty on save.
- The standard safe approach is loading the full aggregate, executing domain behavior, and saving.
- Reduced aggregate-root mapping is a specialized technique for selectively updating root fields; do not equate it with projections.
- Reduced mappings should not be applied to child entities inside an aggregate because child entities may be deleted and re-created, causing unmapped columns to revert to defaults.
- Direct SQL/custom repositories fit intentional partial updates, but you must manually handle optimistic locking, auditing, callbacks, events, validation, and transactions.
- Version is concurrency metadata; do not strip it merely because a projection or API response does not display it.
- Inspect SQL and child data after saving to ensure everything outside the update scope stays intact.

**Projections answer “what needs to be read”; aggregates answer “what is the current domain state.”** Keep those two roles separate. When partial updates are needed, express intent via a command, then choose read-modify-save, reduced root mapping, or controlled custom SQL.

## References

- [Spring Data Relational — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html)
- [Spring Data Relational — Projections](https://docs.spring.io/spring-data/relational/reference/repositories/projections.html)
- [Spring Data JDBC — How Can I Do a Partial Update of an Aggregate Root?](https://spring.io/blog/2022/01/20/spring-data-jdbc-how-can-i-do-a-partial-update-of-an-aggregate-root/)
