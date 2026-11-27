# Distinguishing Unidirectional, Bidirectional Relationships, and the Owning Side

## 1. Relationship Direction in the Entity Model

In JPA, a relationship describes how Entity objects reference each other. There are two ways to organize reference paths in Java:

- **Unidirectional:** only one Entity holds a property referencing the other Entity. For example, `PurchaseOrder` has a `customer` property, while `Customer` does not have an `orders` collection.
- **Bidirectional:** both Entities have properties referencing each other. For example, `PurchaseOrder.customer` and `Customer.orders` represent the same relationship.

Relationship direction in the object model is a separate concept from relationship cardinality in the database. `@ManyToOne`, `@OneToMany`, `@OneToOne`, and `@ManyToMany` describe cardinality; unidirectional/bidirectional describe the reference directions in Java. A many-to-many relationship can still be unidirectional or bidirectional.

You do not have to map a relationship bidirectionally just because the database has a foreign key. If the use case only needs to navigate from an order to a customer, a unidirectional mapping is usually simpler and less error-prone.

## 2. What Is the Owning Side?

In a JPA relationship, the **owning side** is the side that determines updates to the association in the database. For relationships using a foreign key, the owning side is typically the Entity that contains the foreign key property and declares `@JoinColumn`. For relationships using a join table, the owning side is the side that declares `@JoinTable` or the side that does not declare `mappedBy`.

The other side of a bidirectional relationship is the **inverse side**, declared using `mappedBy`. The `mappedBy` value is the name of the Java property on the owning side, which is case-sensitive and is not the database column name.

Example:

```java
// PurchaseOrder owns the relationship because it contains customer_id.
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;

// Customer is the inverse side.
@OneToMany(mappedBy = "customer")
private List<PurchaseOrder> orders = new ArrayList<>();
```

In this example, `mappedBy = "customer"` points to the `PurchaseOrder.customer` property. Hibernate reads the relationship from that property to write `customer_id`. Simply adding an order to `Customer.orders` without assigning `PurchaseOrder.customer` will not update the foreign key as intended.

Important rule: when modifying a bidirectional relationship, update the owning side so the change is persisted; at the same time, update both sides in memory to keep the object graph consistent.

## 3. Unidirectional vs. Bidirectional Relationships: Choosing Based on Need

| Criterion | Unidirectional | Bidirectional |
| --- | --- | --- |
| Navigation paths in Java | One side accesses the other | Accessible from both sides |
| Number of relationship properties | Fewer | More, with circular references |
| Object graph synchronization | Usually simpler | Must keep both sides consistent |
| Suitable use case | Use cases navigating in one direction only | Use cases frequently needing two-way navigation |
| Common risks | Unintended join table mapping with unidirectional OneToMany | Forgetting to update the owning side or hitting cycles during serialization |

Do not create a bidirectional relationship just for the convenience of a single screen or query. You can use a repository query, DTO projection, or JPQL join when data from the other side is needed without adding a reverse collection to the Entity.

## 4. Bidirectional OneToMany/ManyToOne: The ManyToOne Side Owns It

This is the most common pattern. The `customer_id` foreign key resides in the `purchase_order` table, so `PurchaseOrder` owns the relationship:

```java
@Entity
@Table(name = "customer")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(mappedBy = "customer", cascade = CascadeType.PERSIST)
    private List<PurchaseOrder> orders = new ArrayList<>();

    public void addOrder(PurchaseOrder order) {
        orders.add(order);
        order.setCustomer(this);
    }

    public void removeOrder(PurchaseOrder order) {
        orders.remove(order);
        order.setCustomer(null);
    }
}
```

```java
@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    public void setCustomer(Customer customer) {
        this.customer = customer;
    }
}
```

These are the core declarations; in a real application, you should add constructors, getters/setters, and appropriate `equals`/`hashCode` rules. `Customer.orders` uses `mappedBy`, while `PurchaseOrder.customer` contains `@JoinColumn` and is therefore the owning side.

The `addOrder` method updates both the collection and the owning property. If you only call `customer.getOrders().add(order)`, the Java collection may contain the order while `order.customer` remains null; on flush, `customer_id` may not be written as expected. If `nullable = false`, saving may even fail due to a null foreign key.

The `removeOrder` method above is only suitable when the relationship allows disassociation and the foreign key column is nullable. If `customer_id` is NOT NULL, the business logic must define whether to delete the order, reassign it to another customer, or reject the operation. You can use `orphanRemoval = true` if removing an order from the collection means deleting the child Entity, but that is a data lifecycle decision, not a default relationship synchronization mechanism.

## 5. Unidirectional OneToMany

If you only need to access `PurchaseOrder` instances from `Customer` without needing a `PurchaseOrder.customer` property, you can declare a unidirectional `@OneToMany`. By default, JPA typically uses a join table for this mapping:

```java
@OneToMany
@JoinTable(
    name = "customer_order",
    joinColumns = @JoinColumn(name = "customer_id"),
    inverseJoinColumns = @JoinColumn(name = "order_id", unique = true)
)
private List<PurchaseOrder> orders = new ArrayList<>();
```

To use a foreign key on the child table without adding a reverse property, you can declare `@JoinColumn` directly on the collection:

```java
@OneToMany
@JoinColumn(name = "customer_id")
private List<PurchaseOrder> orders = new ArrayList<>();
```

In this unidirectional form, the collection is the side declaring the association; there is no `mappedBy` because the child Entity has no corresponding relationship property. Inspect the DDL generated by Hibernate or existing migrations to ensure the foreign key structure matches the mapping. If you frequently need to navigate from the order back to the customer, consider switching to a bidirectional `ManyToOne`/`OneToMany` mapping.

## 6. OneToOne: The Side Holding the Foreign Key Owns It

For an account and profile relationship, assuming the `profile` table contains `account_id`, `Profile` is the owning side:

```java
@Entity
public class Profile {
    @Id
    private Long id;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "account_id", nullable = false, unique = true)
    private Account account;
}
```

```java
@Entity
public class Account {
    @Id
    private Long id;

    @OneToOne(mappedBy = "account", fetch = FetchType.LAZY)
    private Profile profile;
}
```

`Profile.account` owns the relationship because the `profile` table holds the `account_id` foreign key. `Account.profile` is the inverse side. `unique = true` expresses the schema-level constraint that an account can be linked to at most one profile; a migration creating the corresponding unique constraint is still needed.

If the foreign key is placed on the `account` table instead, swap the owning/inverse positions to match the schema. With OneToOne, the owning side is determined by where the foreign key is stored, not by which Entity appears to be the parent in the business domain.

## 7. ManyToMany: The Owning Side Manages the Join Table

For example, students enroll in many courses and each course has many students. The `student_course` join table stores both foreign keys:

```java
@Entity
public class Student {
    @Id
    private Long id;

    @ManyToMany
    @JoinTable(
        name = "student_course",
        joinColumns = @JoinColumn(name = "student_id"),
        inverseJoinColumns = @JoinColumn(name = "course_id")
    )
    private Set<Course> courses = new HashSet<>();
}
```

```java
@Entity
public class Course {
    @Id
    private Long id;

    @ManyToMany(mappedBy = "courses")
    private Set<Student> students = new HashSet<>();
}
```

`Student.courses` is the owning side because it declares `@JoinTable`; `Course.students` is the inverse side because of `mappedBy = "courses"`. When adding or removing an association, you must update `Student.courses` so Hibernate writes changes to the join table. If keeping both collections in memory, helper methods should synchronize both.

```java
public void addCourse(Course course) {
    courses.add(course);
    course.getStudents().add(this);
}

public void removeCourse(Course course) {
    courses.remove(course);
    course.getStudents().remove(this);
}
```

Avoid indiscriminately using `CascadeType.REMOVE` in ManyToMany: a `Course` can be shared by many `Student` instances, so deleting one student does not mean deleting the course. If the relationship has its own attributes such as enrollment time, grade, or status, create an intermediate Entity such as `Enrollment` instead of using ManyToMany directly.

## 8. Synchronizing Both Sides in Memory

JPA does not automatically guarantee that both Java properties of a bidirectional relationship stay in sync when the application modifies one side. Hibernate relies on the owning side to persist the link. Therefore, add/remove operations should be encapsulated in helper methods on the domain model:

- Adding a relationship: add the element to the collection and assign the owning-side reference.
- Removing a relationship: remove the element from the collection and update the owning side according to business rules.
- Do not let services arbitrarily mutate each collection in multiple places; centralizing synchronization logic prevents inconsistent state.

With bidirectional relationships, `toString()`, `equals()`, and `hashCode()` must avoid traversing the circular relationship. For example, `Customer` references `PurchaseOrder` and `PurchaseOrder` references `Customer`; including both properties in `toString()` can cause recursion. Including mutable collections in `hashCode()` can also break `HashSet` behavior when relationships change. Choose stable identifiers and equality rules suited to the Entity lifecycle.

## 9. Owning Side, cascade, and orphanRemoval Are Three Different Concepts

| Mechanism | Question It Answers |
| --- | --- |
| Owning side / `mappedBy` | Which side determines writing the FK link or join table? |
| `cascade` | Do persist/merge/remove/refresh/detach operations propagate to related Entities? |
| `orphanRemoval` | When a child Entity is removed from a OneToOne/OneToMany relationship, is the child Entity deleted from the database? |

`cascade = PERSIST` does not turn the inverse side into the owning side. `cascade = ALL` also does not automatically synchronize the two Java properties. Likewise, `orphanRemoval = true` does not replace updating the owning side; it expresses a lifecycle rule for the child Entity. Only enable cascade and orphan removal when there is true lifecycle ownership, to avoid accidentally deleting shared data.

## 10. Modifying Relationships and Flushing

With a managed `PurchaseOrder`, changing `order.setCustomer(newCustomer)` updates the owning side. Hibernate will write the new `customer_id` value when flushing or committing the transaction. If you only add the order to `newCustomer.orders` without changing `order.customer`, Hibernate has no owning-side change to write to the foreign key.

With a detached Entity, bring the object back into the persistence context via the proper `merge` flow or load the managed Entity and then modify it. `merge()` returns a different managed instance; continuing to operate on the original detached object does not modify the merged managed instance.

Do not expect SQL to be emitted immediately on a setter call. Hibernate may defer updates until flush/commit. When verification is needed, enable SQL logging in the development environment and observe the `UPDATE` statements or join table operations.

## 11. Fetching and Loops When Returning Entities in an API

Bidirectional relationships create an object graph that can form cycles. When serializing an Entity directly to JSON, the serializer may loop `Customer.orders[0].customer.orders...`, causing infinite recursion or oversized payloads. Use DTOs/projections to define the data the API needs to return; do not let the JSON structure depend entirely on the Entity graph.

Fetch type is also independent of the owning side. By default, JPA specifies `ManyToOne` and `OneToOne` as EAGER, while `OneToMany` and `ManyToMany` are LAZY. EAGER can trigger unexpected queries; LAZY can cause errors when accessed outside a transaction or N+1 queries if no fetch plan is defined. Choose a fetch plan per use case using queries, entity graphs, or projections; do not use `mappedBy` to control fetching.

## 12. Common Errors and Diagnostics

**Adding an element to a collection but the FK does not change.** Check whether the collection is the inverse side with `mappedBy`. Update the owning-side property.

**Wrong name in `mappedBy`.** The value must exactly match the relationship property name on the owning Entity, not a column name like `customer_id`.

**Both sides exist, but only one side shows the new data.** Synchronize both properties in a helper method; the owning side determines what is persisted, while the inverse collection may still be stale in memory.

**Unexpected join table appears.** Check unidirectional `@OneToMany`: by default it may use a join table. If the schema needs a FK on the child table, declare `@JoinColumn` or design a bidirectional relationship with `ManyToOne` owning the FK.

**Deleting a parent removes shared data.** Review `CascadeType.REMOVE` and `orphanRemoval`; they are lifecycle rules, not tools for synchronizing relationships.

**SQL updates are correct, but the API returns looping JSON.** Separate DTOs from Entities and explicitly define the data direction the API exposes.

## 13. Relationship Design Checklist

- Choose unidirectional or bidirectional based on the actual navigation needs of your use cases.
- Determine where the FK or join table lives before declaring the owning side.
- For bidirectional relationships, specify `mappedBy` on the inverse side and point it to the exact Java property.
- Update the owning side and synchronize the object graph with helper methods.
- Decide `cascade` and `orphanRemoval` independently of the owning side.
- Consider the fetch plan, N+1 queries, and serialization cycle risks.
- Verify DDL, foreign keys, unique constraints, and generated SQL against the target database.

Unidirectional vs. bidirectional is an object-model choice; the owning side is the rule for writing the relationship to the database. Understanding both concepts keeps mappings clear, prevents missed FK updates, and aligns Entity lifecycles with business rules.