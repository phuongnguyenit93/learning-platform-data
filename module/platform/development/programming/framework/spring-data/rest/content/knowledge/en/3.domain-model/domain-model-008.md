# Relationship Owning Side, mappedBy, Cascade, and orphanRemoval in JPA

## Objectives

When mapping relationships between entities, JPA needs to know which side decides what relationship state is written to the database, which side holds the back-reference in the object model, and which lifecycle operations propagate to related entities. Four concepts commonly appear together: owning side, mappedBy, cascade, and orphanRemoval.

This lesson explains how to read mappings, how to update bidirectional relationships in Java, how to choose cascade options according to domain lifecycles, and how to use orphanRemoval for child entities whose lifecycle depends on the parent.

## 1. Owning Side and Inverse Side

A bidirectional relationship has two ends for navigation in Java, yet the database relationship has a single primary representation, typically a foreign key or join table. JPA distinguishes:

- **Owning side:** the side responsible for synchronizing relationship changes to the database.
- **Inverse side:** the other navigation end, which declares mappedBy to indicate the attribute on the owning side mapping the same association.

Owning side is a persistence mapping concept, not necessarily the aggregate root, business owner, or the entity with the longer lifecycle.

When the persistence context flushes, the provider uses the owning side to write relationship changes. Modifying only the collection on the inverse side without updating the owning-side reference may result in changes not being persisted as expected.

### Rules by Relationship Type

| Bidirectional Relationship | Owning Side | Inverse Side |
|---|---|---|
| OneToMany / ManyToOne | ManyToOne (the many side) | OneToMany, with mappedBy |
| OneToOne | The side mapping the foreign key | The other side, with mappedBy |
| ManyToMany | One side chosen to map the join table | The other side, with mappedBy |

In a bidirectional OneToMany/ManyToOne relationship, the ManyToOne side is the owning side. Do not place mappedBy on ManyToOne.

### Order and Order Line Relationship Example

Suppose the database has the structure:

~~~text
purchase_order
--------------
id (PK)

order_line
----------
id (PK)
sku
quantity
purchase_order_id (FK -> purchase_order.id)
~~~

The foreign key purchase_order_id resides in the order_line table. Therefore, OrderLine is the owning side; PurchaseOrder is the inverse side.

- OrderLine holds a reference to PurchaseOrder using @ManyToOne and @JoinColumn.
- PurchaseOrder holds a collection of OrderLine using @OneToMany(mappedBy = "purchaseOrder").
- The mappedBy value is the Java attribute name purchaseOrder inside OrderLine.

## 2. mappedBy and JoinColumn

mappedBy may only be declared on the inverse side of a bidirectional OneToOne, OneToMany, or ManyToMany relationship. Its value is the **Java attribute name on the owning side**, not the SQL column name, table name, or class name.

~~~java
// PurchaseOrder: inverse side
@OneToMany(mappedBy = "purchaseOrder")
private List<OrderLine> lines = new ArrayList<>();

// OrderLine: owning side
@ManyToOne
@JoinColumn(name = "purchase_order_id")
private PurchaseOrder purchaseOrder;
~~~

In this example:

- purchaseOrder is the Java field name.
- purchase_order_id is the database column name.
- mappedBy must receive "purchaseOrder".

Attribute names are case-sensitive. If you rename the field on the owning side, you must update the mappedBy value accordingly.

In a typical ManyToOne relationship, @JoinColumn is placed on the ManyToOne side because that is the side mapping the foreign key. The OneToMany side uses mappedBy to point to that field. Do not map the same association with mappedBy on the inverse side alongside an independent @JoinColumn on that same inverse side.

### Unidirectional and Bidirectional Relationships

- **Unidirectional:** only one entity holds a reference or collection to the other entity. The association has one owning side.
- **Bidirectional:** both entities can navigate to each other. One side owns the mapping; the other references the owning field via mappedBy.
- Adding reference fields to both classes does not automatically tell JPA they are two ends of the same association. The corresponding mapping must be declared.

A unidirectional OneToMany may use a join table if no other foreign key mapping is declared. If you want the foreign key in the child table, you can place @JoinColumn on the collection mapping per JPA rules. Determine the desired schema before choosing the mapping style.

## 3. Synchronizing Both Sides in Memory

JPA uses the owning side to persist the relationship, but the application must keep both ends of a bidirectional relationship consistent in memory.

For example, adding a child only to the collection:

~~~java
order.getLines().add(line);
~~~

The collection contains line, yet line.getPurchaseOrder() is still null. Because OrderLine is the owning side, the foreign key may not be written properly.

Encapsulate updating both ends in helper methods:

~~~java
public void addLine(OrderLine line) {
    lines.add(line);
    line.setPurchaseOrder(this);
}

public void removeLine(OrderLine line) {
    if (lines.remove(line)) {
        line.setPurchaseOrder(null);
    }
}
~~~

addLine updates both the collection and the owning reference. removeLine removes the child from the collection and clears the back-reference. Service code calls a single domain method instead of having to remember to update two separate fields.

Guidelines for writing helper methods:

- Place helper methods on the entity managing the collection to encapsulate relationship rules.
- Prevent external code from arbitrarily modifying the collection and forgetting the owning side.
- When moving a child to another parent, handle both the old and new relationships intentionally.
- With orphanRemoval=true, do not treat the child as an entity that can be freely moved between parents.
- If using a Set, design equals and hashCode carefully, especially with auto-generated IDs.
- Avoid applying Lombok @Data mechanically to bidirectional entities because generated equals, hashCode, and toString may traverse cyclic associations or trigger lazy loading.

## 4. Cascade: Propagating Lifecycle Operations

Cascade specifies whether operations on the source entity propagate to referenced target entities. Cascade is declared on the association and propagates from the entity carrying the annotation to the related entity.

By default, JPA cascades no operations. Cascade types:

| Cascade type | Behavior |
|---|---|
| PERSIST | When persisting the source entity, persist cascades to target entities |
| MERGE | When merging the source entity, merge cascades to target entities |
| REMOVE | When removing the source entity, remove cascades to target entities |
| REFRESH | When refreshing the source entity, refresh cascades to target entities |
| DETACH | When detaching the source entity, detach cascades to target entities |
| ALL | Includes PERSIST, MERGE, REMOVE, REFRESH, and DETACH |

Example cascading persist only:

~~~java
@OneToMany(
    mappedBy = "purchaseOrder",
    cascade = CascadeType.PERSIST
)
private List<OrderLine> lines = new ArrayList<>();
~~~

When persisting PurchaseOrder, the persist operation propagates to the OrderLine instances referenced through this association.

Multiple cascade types can be chosen:

~~~java
@OneToMany(
    mappedBy = "purchaseOrder",
    cascade = {CascadeType.PERSIST, CascadeType.MERGE}
)
private List<OrderLine> lines = new ArrayList<>();
~~~

Or use CascadeType.ALL when the child's lifecycle truly depends on the parent:

~~~java
@OneToMany(
    mappedBy = "purchaseOrder",
    cascade = CascadeType.ALL
)
private List<OrderLine> lines = new ArrayList<>();
~~~

ALL is the set of cascade types listed above. It does not mean cascading every query, every transaction, or every HTTP operation.

### Choosing Cascade Based on Domain Lifecycle

Cascade is usually appropriate when the target entity only makes sense within the scope of the source entity. For example, OrderLine typically belongs to one PurchaseOrder; when saving a new order, we want its new lines persisted along with it.

Do not enable cascade blindly:

- If the target entity is shared by multiple other entities, cascade REMOVE can delete data still referenced elsewhere.
- With ManyToMany such as Student–Course, deleting a Student should normally remove only join table rows; do not cascade REMOVE and delete a Course shared by other Students.
- Cascade does not eliminate the need to distinguish transient, managed, and detached entities.
- PERSIST on a detached entity can result in an EntityExistsException or PersistenceException at flush/commit.
- MERGE copies state to a managed instance; after merging, use the returned instance or work within the persistence context properly.

A helpful question when choosing cascade options is: if a lifecycle operation is executed on the source entity, should the target entity undergo the same operation? Add only the cascade types that match that answer.

According to Jakarta Persistence, cascade REMOVE should only be applied to OneToOne or OneToMany associations to ensure portability. Applying it to ManyToMany or other associations is not portable across providers.

## 5. orphanRemoval: Deleting Entities When Disconnected from a Relationship

orphanRemoval is an option on OneToOne and OneToMany. When a target entity is removed from the relationship—for example, removed from a collection or its reference is set to null—JPA applies the remove operation to the orphaned entity. Deletion executes when the persistence context flushes.

~~~java
@OneToMany(
    mappedBy = "purchaseOrder",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
~~~

When an OrderLine is removed from PurchaseOrder via the helper method, JPA deletes the child entity from the database at flush/commit. There is no need to call repository.delete(line) separately in this case.

### Differences Between Cascade REMOVE and orphanRemoval

| Scenario | Cascade REMOVE | orphanRemoval |
|---|---|---|
| Deleting the source entity | Propagates remove to target entities if cascade REMOVE is set | Remove on source also propagates to target per JPA rules |
| Only removing child from collection | Does not automatically delete child just because association was removed | Deletes orphaned child at flush |
| Setting reference to null | Does not automatically delete child just because reference was cleared | Deletes orphaned child at flush |
| Portable association scope | Should be used with OneToOne/OneToMany | Only supported on OneToOne/OneToMany |

orphanRemoval=true already includes deleting targets when the parent is removed per JPA rules. You do not need to add cascade=REMOVE solely for that behavior; other cascades such as PERSIST or MERGE may still be needed.

### Use Only for Children with Parent-Dependent Lifecycles

orphanRemoval indicates that the child is exclusively owned by the parent and has no independent lifecycle. For example:

- OrderLine belongs exclusively to one PurchaseOrder.
- AddressDetail belongs exclusively to one CustomerProfile.
- TaskStep belongs exclusively to one WorkflowDefinition.

Do not use orphan removal for entities shared independently across multiple parents. When a child is removed from one relationship, deleting it can corrupt data elsewhere.

Portable applications should not rely on a specific deletion order, nor reassign an orphaned entity to another relationship or attempt to re-persist it. Orphan removal rules do not apply to targets that are detached, new, or already removed.

### orphanRemoval Is Not ON DELETE CASCADE

The two mechanisms operate at different layers:

- **JPA cascade/orphanRemoval:** the persistence provider manages entity lifecycles inside the persistence context.
- **Foreign key ON DELETE CASCADE:** the database automatically deletes related rows when the referenced row is deleted.

A system may use one or both, but should not assume they are equivalent. Bulk JPQL deletes also bypass individual entity lifecycles in the persistence context; do not expect cascade/orphanRemoval to run the same way as removing managed entities with EntityManager.remove.

## 6. Complete Example: PurchaseOrder and OrderLine

Illustrated model:

- PurchaseOrder is the parent.
- OrderLine is an exclusive child of one order.
- The foreign key resides in the order_line table.
- OrderLine is the owning side.
- PurchaseOrder is the inverse side via mappedBy.
- Cascade ALL saves/deletes children alongside the parent.
- Orphan removal deletes children when removed from the collection.

### 6.1. Schema

~~~text
purchase_order
--------------
id              PK

order_line
----------
id              PK
sku
quantity
purchase_order_id  FK -> purchase_order.id
~~~

### 6.2. PurchaseOrder Entity

~~~java
import jakarta.persistence.CascadeType;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(
        mappedBy = "purchaseOrder",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }

    public void addLine(OrderLine line) {
        Objects.requireNonNull(line, "line must not be null");

        if (line.getPurchaseOrder() != null
                && line.getPurchaseOrder() != this) {
            throw new IllegalArgumentException(
                "OrderLine already belongs to another order"
            );
        }

        if (!lines.contains(line)) {
            lines.add(line);
            line.setPurchaseOrder(this);
        }
    }

    public void removeLine(OrderLine line) {
        if (lines.remove(line)) {
            line.setPurchaseOrder(null);
        }
    }
}
~~~

### 6.3. OrderLine Entity

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "order_line")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String sku;

    private int quantity;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "purchase_order_id", nullable = false)
    private PurchaseOrder purchaseOrder;

    protected OrderLine() {
    }

    public OrderLine(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public PurchaseOrder getPurchaseOrder() {
        return purchaseOrder;
    }

    void setPurchaseOrder(PurchaseOrder purchaseOrder) {
        this.purchaseOrder = purchaseOrder;
    }
}
~~~

Note the two annotations:

- @OneToMany is on PurchaseOrder and uses mappedBy = "purchaseOrder".
- @ManyToOne is on OrderLine and uses @JoinColumn to map the foreign key.

Only OrderLine determines the purchase_order_id value written to the database. PurchaseOrder's helper methods update both the collection and this reference.

### 6.4. Repository and Service

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {
}
~~~

~~~java
import java.util.Objects;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Long createOrder() {
        PurchaseOrder order = new PurchaseOrder();
        order.addLine(new OrderLine("KB-01", 2));
        order.addLine(new OrderLine("MS-02", 1));

        return repository.save(order).getId();
    }

    @Transactional
    public void removeLine(Long orderId, Long lineId) {
        PurchaseOrder order = repository.findById(orderId)
            .orElseThrow();

        OrderLine line = order.getLines().stream()
            .filter(item -> Objects.equals(item.getId(), lineId))
            .findFirst()
            .orElseThrow();

        order.removeLine(line);
        // orphanRemoval deletes the OrderLine when the persistence context flushes.
    }
}
~~~

In createOrder, saving a new PurchaseOrder persists the OrderLine instances via cascade PERSIST, which is part of ALL. When removeLine runs in a transaction, the entity is managed; dirty checking detects the collection change and orphanRemoval triggers deletion of the child at flush/commit. Calling save again on the parent is unnecessary in this case.

### 6.5. Dependencies and Test Configuration

The Maven example uses Spring Boot 3.5.16 and Java 17. Spring Boot manages starter versions:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Create the application class in a parent package of the entities and repository:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JpaDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(JpaDemoApplication.class, args);
    }
}
~~~

For local demos, configure H2 in-memory:

~~~properties
spring.datasource.url=jdbc:h2:mem:orders;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
~~~

In production, manage the schema with a migration tool such as Flyway or Liquibase and do not keep credentials in source code.

### 6.6. Testing orphanRemoval

An integration test with @DataJpaTest verifies that the child is deleted after removal from the collection:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class PurchaseOrderRelationshipTest {

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void removesLineWhenItIsRemovedFromOrder() {
        PurchaseOrder order = new PurchaseOrder();
        OrderLine line = new OrderLine("KB-01", 2);
        order.addLine(line);

        entityManager.persist(order);
        entityManager.flush();

        Long orderId = order.getId();
        Long lineId = line.getId();

        entityManager.clear();

        PurchaseOrder managedOrder =
            entityManager.find(PurchaseOrder.class, orderId);
        OrderLine managedLine =
            entityManager.find(OrderLine.class, lineId);

        assertThat(managedLine.getPurchaseOrder().getId())
            .isEqualTo(orderId);

        managedOrder.removeLine(managedLine);
        entityManager.flush();
        entityManager.clear();

        assertThat(entityManager.find(OrderLine.class, lineId))
            .isNull();
    }
}
~~~

Run tests with Maven:

~~~bash
mvn test
~~~

The test uses H2 from the dependencies above. It creates an order with a line item, flushes to write the foreign key, reloads entities in a fresh persistence context, removes the child, and flushes again. It then queries for the child to verify the entity has been deleted.

## 7. Owning Side in OneToOne and ManyToMany

### OneToOne

With OneToOne, the owning side is the side mapping the foreign key. For example, the app_user table has a profile_id column:

~~~java
@Entity
public class AppUser {

    @OneToOne
    @JoinColumn(name = "profile_id", unique = true)
    private UserProfile profile;
}
~~~

The UserProfile side is the inverse side:

~~~java
@Entity
public class UserProfile {

    @OneToOne(mappedBy = "profile")
    private AppUser user;
}
~~~

mappedBy = "profile" points to the profile field in AppUser. If the foreign key resides in the other table, the owning side changes accordingly with the database mapping.

### ManyToMany

With ManyToMany, the application picks one side as the owning side. The owning side typically declares the join table:

~~~java
@Entity
public class Student {

    @ManyToMany
    @JoinTable(
        name = "student_course",
        joinColumns = @JoinColumn(name = "student_id"),
        inverseJoinColumns = @JoinColumn(name = "course_id")
    )
    private Set<Course> courses = new HashSet<>();
}
~~~

The Course side declares the inverse:

~~~java
@Entity
public class Course {

    @ManyToMany(mappedBy = "courses")
    private Set<Student> students = new HashSet<>();
}
~~~

When adding or removing a Student–Course relationship, update the owning side and synchronize the inverse side in memory. Removing a typical ManyToMany link only deletes the join table row, not the Student or Course. Avoid cascade REMOVE between entities that can be shared by multiple objects.

If a ManyToMany relationship carries extra attributes such as enrollment timestamp, grade, role, or status, consider converting the join table into a dedicated link entity, such as Enrollment. The association then has its own lifecycle and data.

## 8. Fetch, Cascade, and Ownership Are Separate Concerns

| Concept | Question |
|---|---|
| Owning side | Which side decides how the relationship is persisted to the database? |
| mappedBy | Which owning-side attribute does the inverse side reference? |
| cascade | Which lifecycle operations propagate to related entities? |
| orphanRemoval | Is the entity deleted when detached from the relationship? |
| fetch | When loading an entity, when is the association loaded? |

For example, @ManyToOne defaults to EAGER in JPA, while @OneToMany defaults to LAZY. Fetch strategy does not determine the owning side and does not enable cascade. Choose data loading strategies per use case to avoid loading overly large entity graphs or encountering N+1 queries.

## 9. Common Issues to Watch Out For

- **Modifying only the inverse collection:** the owning side has not changed, so the foreign key is not updated as expected. Use helper methods that update both ends.
- **Pointing mappedBy to a column name:** mappedBy must point to the Java attribute name on the owning entity, not the SQL column name.
- **Placing mappedBy on ManyToOne:** in a bidirectional OneToMany/ManyToOne relationship, ManyToOne is the owning side.
- **Declaring JoinColumn on both sides:** can create conflicting mappings for the same association.
- **Cascade ALL on shared entities:** deleting a parent can delete entities still referenced by other parents.
- **Cascade REMOVE on ManyToMany:** risks deleting shared target entities and is not portable in JPA.
- **orphanRemoval on shared entities:** unlinking from one parent can delete data needed elsewhere.
- **Removing a child without clearing the owning reference:** memory and database can become inconsistent.
- **Forgetting transactions:** lazy collections may be inaccessible outside a persistence context; dirty checking requires flushing within a transaction.
- **Assuming orphanRemoval deletes immediately:** the remove operation applies at flush, typically at the end of the transaction or upon calling flush.
- **Bulk JPQL deletes:** do not pass through individual entity lifecycles like EntityManager.remove.
- **Unsuitable equals/hashCode:** Set collections may add or remove entities unexpectedly when IDs are auto-generated or equality changes after persisting.

## 10. References

- [Jakarta Persistence 3.2 Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): owning/inverse side, mappedBy, cascade, and orphanRemoval.
- [Jakarta Persistence — OneToMany API](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/onetomany): cascade, mappedBy, fetch, and orphanRemoval.
- [Jakarta Persistence — ManyToOne API](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/manytoone): many-side mapping and foreign key.
- [Hibernate ORM User Guide — Associations](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html): bidirectional associations, helper methods, orphan removal, and SQL.
- [Spring Data JPA Reference — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html): transaction boundaries when using Spring Data JPA.
- [Spring Boot 3.5 — Data Access](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html): data access and JPA configuration in Spring Boot.

Design ownership and lifecycle from the domain model before choosing cascade rules. When mappings reflect true relationships, saving, unlinking, and deleting entities become far more predictable.