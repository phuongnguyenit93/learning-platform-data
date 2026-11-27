# Synchronizing Both Sides of a Relationship with Business Methods

## Objectives

After this lesson, you will be able to:

- Explain why a bidirectional relationship in JPA has two object references while typically only one side owns the relationship in the database.
- Identify the owning side and inverse side via `mappedBy`.
- Write business methods to add, remove, and update relationships while always keeping both sides synchronized in memory.
- Distinguish `cascade` from `orphanRemoval` and choose the right lifecycle for child entities.
- Test object graph state, persisted foreign keys, and orphan deletion behavior.
- Avoid common errors such as updating only the inverse side, mutating collections directly, creating JSON serialization loops, or triggering N+1 queries.

## 1. Why Synchronize Both Sides?

JPA allows modeling bidirectional relationships between entities. For example, an order has many order lines, and each order line knows which order it belongs to.

In Java, that relationship has two navigation paths:

- From the order to its lines: `order.getLines()`.
- From an order line to its order: `line.getOrder()`.

These two references describe the same business relationship. If code adds a line to the order's collection without setting the order back on the line, the in-memory object graph becomes inconsistent.

Buggy example:

~~~java
order.getLines().add(line);
// line.getOrder() is still null
~~~

Conversely:

~~~java
line.setOrder(order);
// order.getLines() does not contain line yet
~~~

In both cases, the two sides of the relationship are out of sync. This can cause business code to read different results depending on traversal direction and leave the object state out of line with the intended data.

A clean organization is to encapsulate relationship-modifying operations in business methods such as `addLine()`, `removeLine()`, `assignTo()`, or `enroll()`. That method updates both sides and protects domain invariants.

## 2. Owning Side and Inverse Side

Synchronizing the object graph and writing the relationship to the database are two related but distinct concerns.

In JPA, the owning side is the side that determines the foreign key value or join table records. In a common one-to-many relationship:

- `@ManyToOne` on the child entity is typically the owning side because it holds the foreign key.
- `@OneToMany(mappedBy = "...")` on the parent entity is the inverse side because it points to the owning-side property.

Example:

~~~java
@Entity
public class PurchaseOrder {
    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();
}

@Entity
public class OrderLine {
    @ManyToOne
    @JoinColumn(name = "order_id")
    private PurchaseOrder order;
}
~~~

Here `mappedBy = "order"` points to the Java property name `order` in the `OrderLine` entity, not the `order_id` column name.

If you only add an element to the `PurchaseOrder.lines` collection without updating `OrderLine.order`, the provider does not have the proper owning-side value to write the foreign key. Conversely, if you only update `OrderLine.order`, the foreign key may be written properly, but the `PurchaseOrder.lines` collection in memory still does not reflect the relationship.

Therefore, with bidirectional relationships, always update both sides within the same business operation. The owning side determines what relationship data is persisted; helper methods ensure the object graph remains consistent.

### Rules for Relationship Types

| Relationship | Common owning side | Inverse side |
|---|---|---|
| One-to-many / many-to-one | `@ManyToOne` on the many side | `@OneToMany(mappedBy = ...)` on the one side |
| One-to-one | Side with `@JoinColumn` | Side with `mappedBy` |
| Many-to-many | Side declaring `@JoinTable` or without `mappedBy` | Side declaring `mappedBy` |

There is no rule that collections are always the owning side. Read the mapping and determine where the foreign key or join table is placed.

## 3. Main Example: PurchaseOrder and OrderLine

Suppose an order has many order lines. Each order line belongs to only one order. An order line has no independent meaning once removed from an order, so the model uses `orphanRemoval = true`.

### Parent Entity: PurchaseOrder

~~~java
package com.example.orders;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
        // Required by JPA
    }

    public Long getId() {
        return id;
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }

    public void addLine(OrderLine line) {
        Objects.requireNonNull(line, "line must not be null");

        if (line.getOrder() != null && line.getOrder() != this) {
            throw new IllegalArgumentException(
                "OrderLine already belongs to another order"
            );
        }

        if (lines.contains(line)) {
            return;
        }

        lines.add(line);
        line.attachTo(this);
    }

    public void removeLine(OrderLine line) {
        if (lines.remove(line)) {
            line.attachTo(null);
        }
    }
}
~~~

### Child Entity: OrderLine

~~~java
package com.example.orders;

import java.util.Objects;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(nullable = false, length = 40)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {
        // Required by JPA
    }

    public OrderLine(String sku, int quantity) {
        this.sku = Objects.requireNonNull(sku, "sku must not be null");
        if (sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        this.quantity = quantity;
    }

    public Long getId() {
        return id;
    }

    public PurchaseOrder getOrder() {
        return order;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    // Package-private: relationship changes go through PurchaseOrder.
    void attachTo(PurchaseOrder order) {
        this.order = order;
    }
}
~~~

In this example:

- `OrderLine.order` is the owning side and contains the `order_id` foreign key.
- `PurchaseOrder.lines` is the inverse side due to `mappedBy = "order"`.
- `addLine()` adds to the collection and sets the owning side.
- `removeLine()` removes from the collection and clears the reverse reference in the object graph.
- `getLines()` returns an unmodifiable view so external code cannot bypass the helper methods.
- `orphanRemoval = true` indicates the order line is a dependent entity of the order; when removed from a managed parent's collection, it is marked for deletion on flush.
- `cascade = CascadeType.ALL` fits this aggregate model because order lines have a lifecycle owned by the order.

This example uses Java 17+ and Jakarta Persistence, fitting the Spring Boot 3 / Spring Framework 6 stack. The entities are placed in the same package so the parent entity can call the package-private `attachTo()` method. The sample code consists of two separate entity files, not a standalone runnable Java program without JPA dependencies and database configuration.

### Why Avoid Public Setters for the Relationship?

If code anywhere can call `line.setOrder(order)` or mutate the collection directly, synchronization rules become scattered. A service might forget to update the other side or assign a line to a different order without checking invariants.

Restricting relationship setters to package visibility or exposing only business methods lets the domain model control how relationships change. Cases requiring reassignment should be modeled as an explicit business operation that validates state and lifecycle rules.

## 4. Using Business Methods to Protect Invariants

A helper method is not just two lines of add/remove. It is the place to protect domain rules.

For example, an order might only accept order lines when in the `DRAFT` status:

~~~java
public void addLine(OrderLine line) {
    if (status != OrderStatus.DRAFT) {
        throw new IllegalStateException(
            "Only draft orders can be changed"
        );
    }

    Objects.requireNonNull(line, "line must not be null");

    if (line.getOrder() != null && line.getOrder() != this) {
        throw new IllegalArgumentException(
            "OrderLine already belongs to another order"
        );
    }

    if (lines.contains(line)) {
        return;
    }

    lines.add(line);
    line.attachTo(this);
}
~~~

Invariants may include:

- Not adding order lines to a confirmed or paid order.
- Quantity must be greater than 0.
- An order line belongs to only one order.
- An order must have at least one order line before confirmation.
- Not deleting order lines after an invoice has been issued.
- Total amount is calculated from the order lines or updated under a consistent rule.

If an operation needs to modify multiple entities, execute it inside a transaction. Helper methods protect the in-memory object graph; transactions ensure changes commit or roll back together.

### Avoid Moving an Orphan to Another Parent

With `orphanRemoval = true`, removing a child entity from its parent carries the semantics of deleting the child entity on flush. Do not call `removeLine()` and immediately add the same entity to another parent as a routine transfer operation. Hibernate may mark the entity for deletion, leading to errors or unexpected behavior.

If business logic truly requires transferring an order line between two orders, define explicit state transition and lifecycle rules. You may need to remove `orphanRemoval`, design a dedicated transfer operation, or create a new entity per domain rules. Never reuse an orphan-deleting helper for reparenting.

## 5. How Do Cascade and orphanRemoval Differ?

These two attributes are often used together but have different meanings.

**Cascade** determines whether operations on the parent propagate to the child.

- `PERSIST`: persisting the parent can persist the child.
- `MERGE`: merging the parent can merge the child.
- `REMOVE`: removing the parent can remove the child.
- `REFRESH`, `DETACH`: propagate the corresponding operations.

**orphanRemoval** determines whether a child entity is deleted when it is no longer associated with the parent. It typically fits dependent entities that do not exist independently outside the aggregate.

In the `PurchaseOrder`/`OrderLine` example:

- `cascade = ALL` allows persisting, merging, and removing order lines together with the order.
- `orphanRemoval = true` causes calling `order.removeLine(line)` to delete the order line from the database on flush.

Do not use `CascadeType.REMOVE` or `orphanRemoval` for entities shared by multiple parents such as `Product`, `Category`, or `Role`. Removing an association does not mean deleting the shared entity.

If you omit `orphanRemoval` and only set `line.order = null`, the `order_id` column must allow nulls. With `optional = false` and `nullable = false`, that operation is invalid unless the child is deleted or assigned to another parent before flush.

## 6. Bidirectional Relationships in Many-to-Many

In many-to-many, an object can be linked to multiple objects on the other side, such as `Student` and `Course`.

If the relationship is purely a link with no attributes of its own, `@ManyToMany` can be used. Both sides should have helper methods to update both collections.

Illustrative example on the `Student` side:

~~~java
@Entity
public class Student {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToMany
    @JoinTable(
        name = "student_courses",
        joinColumns = @JoinColumn(name = "student_id"),
        inverseJoinColumns = @JoinColumn(name = "course_id")
    )
    private Set<Course> courses = new HashSet<>();

    public void enroll(Course course) {
        Objects.requireNonNull(course, "course must not be null");
        if (courses.add(course)) {
            course.addStudentFromStudent(this);
        }
    }

    public void drop(Course course) {
        if (courses.remove(course)) {
            course.removeStudentFromStudent(this);
        }
    }
}
~~~

The `Course` side holds the inverse collection:

~~~java
@Entity
public class Course {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToMany(mappedBy = "courses")
    private Set<Student> students = new HashSet<>();

    void addStudentFromStudent(Student student) {
        students.add(student);
    }

    void removeStudentFromStudent(Student student) {
        students.remove(student);
    }
}
~~~

In this example, `Student` is the owning side because it declares `@JoinTable`; `Course` is the inverse side due to `mappedBy = "courses"`. `enroll()` updates both collections. The internal methods on `Course` do not call back into `student.enroll()`, preventing infinite recursion.

Do not use `CascadeType.REMOVE` for typical many-to-many relationships. A `Course` may be enrolled in by many `Student` instances; deleting one `Student` must not delete the `Course`. When removing a link, delete the join table row, not the entity still in use.

If the relationship has attributes such as `enrolledAt`, `grade`, `status`, or `role`, create an intermediate entity such as `Enrollment` with two many-to-one relationships instead of a plain many-to-many.

## 7. One-to-One and Many-to-One

The principle of synchronizing both sides also applies to other relationship types.

### One-to-One

One side containing `@JoinColumn` is the owning side; the other side uses `mappedBy`. Helper methods need to set both references and enforce rules for replacing an old link.

If the entity depends completely on the parent, consider `orphanRemoval`. If both entities have independent lifecycles, do not enable `orphanRemoval` just because they happen to be created together right now.

### Many-to-One

A many-to-one relationship often only requires the child to know its parent. You do not necessarily need a reverse collection on the parent if the business logic does not need reverse traversal. A unidirectional relationship is usually simpler and reduces the chance of accidentally loading a large collection.

Only add an inverse collection when there is an actual query or domain operation requirement. A bidirectional relationship is not automatically better than a unidirectional one.

## 8. Cascade, Dirty Checking, and Transactions

When the parent and child are managed in the same persistence context, changes to the owning-side property are detected by Hibernate via dirty checking and written to the database on flush.

Example:

~~~java
@Transactional
public Long createOrder() {
    PurchaseOrder order = new PurchaseOrder();
    order.addLine(new OrderLine("SKU-001", 2));
    order.addLine(new OrderLine("SKU-002", 1));

    PurchaseOrder saved = orderRepository.save(order);
    return saved.getId();
}
~~~

Because the relationship uses `PERSIST` cascading, persisting a new order also persists its order lines. You do not need to call `repository.save()` separately for each line.

With a managed parent, simply calling the helper method inside a transaction allows JPA dirty checking to persist the change. If the object is detached, mutating it does not automatically write to the database. Merge the aggregate properly or load the parent into the persistence context and then invoke the business method.

Do not rely on calling `save()` repeatedly to fix an inconsistent object graph. Before saving, ensure both the owning side and inverse side have been updated properly.

## 9. Queries, Fetching, and Performance

Synchronizing both sides does not mean you should always load both sides.

- `@ManyToOne` defaults to `EAGER` per Jakarta Persistence; consider specifying `LAZY` and loading per use case.
- `@OneToMany` defaults to `LAZY`.
- Accessing collections inside loops can trigger N+1 queries.
- Loading two collections simultaneously with join fetch can multiply result rows and produce duplicate data in SQL.

When you need to read a parent along with its children, use `@EntityGraph` or a fetch join suited to the query. Do not change global fetch types just to fix a single screen. Design queries per use case and measure query counts.

If an API returns entities directly, bidirectional relationships can cause serialization loops: Order contains Lines, and each Line contains Order. Use DTOs or dedicated mappings at the API layer rather than letting the serializer traverse the entire entity graph. Annotations such as `@JsonManagedReference` and `@JsonBackReference` can handle some Jackson cases, but DTOs generally make the contract clearer.

## 10. Testing Relationship Synchronization

An integration test should verify both sides in memory and confirm that the foreign key is persisted properly.

Repository:

~~~java
package com.example.orders;

import java.util.Optional;

import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(attributePaths = "lines")
    Optional<PurchaseOrder> findWithLinesById(Long id);
}
~~~

Test:

~~~java
package com.example.orders;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;

import jakarta.persistence.EntityManager;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class PurchaseOrderRelationshipTest {

    @Autowired
    PurchaseOrderRepository orderRepository;

    @Autowired
    EntityManager entityManager;

    @Test
    void addLineSynchronizesBothSidesAndPersistsForeignKey() {
        PurchaseOrder order = new PurchaseOrder();
        OrderLine line = new OrderLine("SKU-001", 2);

        order.addLine(line);

        assertEquals(1, order.getLines().size());
        assertSame(order, line.getOrder());

        PurchaseOrder saved = orderRepository.saveAndFlush(order);
        Long orderId = saved.getId();

        entityManager.clear();

        PurchaseOrder loaded =
                orderRepository.findWithLinesById(orderId).orElseThrow();

        OrderLine loadedLine = loaded.getLines().get(0);

        assertEquals(1, loaded.getLines().size());
        assertSame(loaded, loadedLine.getOrder());
    }
}
~~~

The test uses `@DataJpaTest` and assumes the test database configuration and two entities from earlier sections. After flushing and clearing the persistence context, the test reloads the aggregate to verify the relationship was written to the database. Checking only the two references before saving proves the in-memory object graph, not that the foreign key was persisted.

You can add an orphan deletion test:

1. Create an order with one order line.
2. Persist and flush.
3. Call `order.removeLine(line)` on the managed parent.
4. Flush.
5. Verify the order line is no longer in the database.

This test confirms `orphanRemoval` works with the actual configuration.

## 11. Common Errors

| Symptom | Cause | Solution |
|---|---|---|
| Collection has child but foreign key is unchanged | Only modified the inverse side | Update the owning side inside the helper method |
| Foreign key is correct but Java collection lacks child | Only modified the owning side | Update the inverse collection as well |
| Child deleted unexpectedly | Inappropriate `orphanRemoval` or `CascadeType.REMOVE` | Identify child lifecycle and configure cascade intentionally |
| Adding child to another parent fails | Child already belonged to old parent; `orphanRemoval` marked it for deletion | Do not reuse remove to transfer parents; design a dedicated transfer |
| Infinite JSON serialization loop | Bidirectional relationship creates a reference cycle | Return DTOs or configure serialization intentionally |
| N+1 queries when reading parent and children | Accessing lazy collection inside a loop | Use `EntityGraph`/fetch join per use case and measure queries |
| Entity relationships updated inconsistently | Public setters and collections allow arbitrary mutation | Encapsulate changes in business methods |
| Test sees correct object graph but DB is wrong | Asserting only before flush or without clearing persistence context | Flush, clear, and reload the entity to verify |

## Pre-Merge Checklist

- [ ] Identified owning side and inverse side from the mapping.
- [ ] `mappedBy` points to the exact Java property name on the owning side.
- [ ] Helper methods update both sides.
- [ ] Collections cannot be mutated directly from outside the aggregate.
- [ ] `cascade` and `orphanRemoval` accurately reflect the child entity's lifecycle.
- [ ] `orphanRemoval` is not used to move a child to another parent.
- [ ] Transactions encompass aggregate changes.
- [ ] Fetch plan avoids N+1 queries and does not load unnecessary collections.
- [ ] APIs do not serialize bidirectional entity cycles.
- [ ] Integration tests flush, clear, and reload to verify foreign keys.

## Conclusion

In a bidirectional JPA relationship, the owning side determines the foreign key or join table written to the database, while helper methods keep the in-memory object graph consistent. For one-to-many/many-to-one, the many-to-one side is typically the owning side; the collection on the one-to-many side uses `mappedBy`. Encapsulate adding and removing relationships in business methods, choose `cascade` and `orphanRemoval` based on real lifecycles, and test by flushing and reloading entities. Doing so prevents two-sided state drift, foreign key bugs, and unintended deletions.