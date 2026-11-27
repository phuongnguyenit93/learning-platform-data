# Derived Identity with @MapsId in Spring Data JPA

In JPA, an entity can use another entity's primary key as all or part of its own primary key. This mapping style is called derived identity. The `@MapsId` annotation expresses that relationship: the relationship's foreign key simultaneously participates in the dependent entity's primary key.

Classic examples are a user profile sharing the same ID as the user, or an order line whose primary key combines the order ID and a line number. `@MapsId` lets JPA synchronize the primary key portion from the relationship, avoiding mapping the same foreign key column in two independent ways.

This lesson uses Java 17+, Spring Boot 3.x, and Jakarta Persistence. JPA imports in the examples use `jakarta.persistence`. For older Spring Boot 2.x projects, the corresponding namespace is typically `javax.persistence`; never mix the two namespaces within the same entity model.

## 1. What Is Derived Identity?

Suppose a system has two tables:

- `app_users` stores users, each having primary key `id`.
- `user_profiles` stores extended profile details; a profile belongs to a single user and has no independent identity.

If `user_profiles.user_id` is both the primary key and a foreign key referencing `app_users.id`, the profile's ID is the user's ID.

| app_users | user_profiles |
|---|---|
| `id` — PK | `user_id` — PK, FK |
| `email` | `bio` |

For example, if a user has ID 41, that user's profile also has ID 41. There is no separate independent ID for the profile.

Derived identity has two common forms:

1. The relationship supplies the dependent entity's entire primary key, typically a One-to-One shared primary key.
2. The relationship supplies part of the primary key, typically a Many-to-One combined with another component in `@EmbeddedId`.

## 2. What Is @MapsId Used For?

`@MapsId` marks a `@OneToOne` or `@ManyToOne` relationship property whose foreign key maps into all or part of the current entity's primary key.

There are two main ways to use it:

- `@MapsId` with no value: the relationship maps to the dependent entity's entire primary key.
- `@MapsId("attributeName")`: the relationship maps to the correspondingly named attribute inside an `@EmbeddedId` embedded primary key.

The name passed to `@MapsId` is the Java property name inside the ID class, not the SQL column name. The mapped ID attribute's type must be compatible with the referenced entity's primary key type.

`@MapsId` does not create cascades automatically, does not manage transactions, and does not replace database foreign key constraints. It describes how JPA maps the dependent entity's key from the relationship.

## 3. One-to-One: Profile Sharing the User's ID

### 3.1. Parent Entity AppUser

Create `AppUser.java`:

~~~java
package com.example.mapsid;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "app_users")
public class AppUser {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 150)
    private String email;

    protected AppUser() {
    }

    public AppUser(String email) {
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
~~~

`AppUser` is the parent entity and auto-generates its primary key via database identity. Before persisting, the ID may not have a value yet; after the entity is persisted, the JPA provider obtains the database-assigned ID.

### 3.2. Dependent Entity UserProfile

Create `UserProfile.java`:

~~~java
package com.example.mapsid;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.MapsId;
import jakarta.persistence.OneToOne;
import jakarta.persistence.Table;
import java.util.Objects;

@Entity
@Table(name = "user_profiles")
public class UserProfile {

    @Id
    @Column(name = "user_id")
    private Long id;

    @MapsId
    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false)
    private AppUser user;

    @Column(length = 500)
    private String bio;

    protected UserProfile() {
    }

    public UserProfile(AppUser user, String bio) {
        this.user = Objects.requireNonNull(user);
        this.bio = bio;
    }

    public Long getId() {
        return id;
    }

    public AppUser getUser() {
        return user;
    }

    public String getBio() {
        return bio;
    }
}
~~~

Key points:

- `@Id` designates the primary key of `UserProfile`.
- `@Column(name = "user_id")` maps the ID property to the `user_id` column.
- `@OneToOne` declares the one-to-one relationship from profile to user.
- `@JoinColumn(name = "user_id")` specifies the foreign key column in `user_profiles`.
- `@MapsId` states that the profile's primary key is derived from `user`'s primary key.
- There is no `@GeneratedValue` on `UserProfile.id` because the profile's ID is inherited from the user.

The same `user_id` column serves as both the primary key and the foreign key. `@MapsId` tells JPA this is a unified mapping rather than two independent properties writing to the same column.

Logical structure of the profile table:

~~~sql
create table user_profiles (
    user_id bigint not null primary key,
    bio varchar(500),
    constraint fk_user_profile_user
        foreign key (user_id) references app_users(id)
);
~~~

Because the primary key is also the foreign key, each user can have at most one profile. This relationship does not automatically force every user to have a profile; if required by the business, enforce that in creation workflows or via appropriate database rules.

### 3.3. Creating a User and Profile

Use `EntityManager` to make the persistence order explicit. Create `ProfileService.java`:

~~~java
package com.example.mapsid;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProfileService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public Long createUserWithProfile(String email, String bio) {
        AppUser user = new AppUser(email);
        entityManager.persist(user);

        // With IDENTITY, persist typically executes INSERT to obtain the ID.
        entityManager.flush();

        UserProfile profile = new UserProfile(user, bio);
        entityManager.persist(profile);

        entityManager.flush();
        return profile.getId();
    }
}
~~~

Execution flow:

1. Create the `AppUser` entity.
2. Persist the user so JPA manages it and obtains its primary key.
3. Create `UserProfile` referencing the managed user.
4. Persist the profile.
5. JPA copies `user.id` into `UserProfile.id` per `@MapsId`.
6. Flush synchronizes changes to the database; the transaction commits when the method completes successfully.

`flush()` clarifies when writes and ID retrieval occur in this example. Flushing is not committing; the transaction can still roll back if an error occurs before completion.

Repositories can be used instead of `EntityManager`. What matters is that the parent entity is persisted or validly cascade-persisted, and the relationship is assigned on the dependent entity before saving.

### 3.4. Testing the Shared Primary Key

Test example using `@DataJpaTest` and `TestEntityManager`:

~~~java
package com.example.mapsid;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class UserProfileMappingTest {

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void profileUsesTheUsersPrimaryKey() {
        AppUser user = new AppUser("linh@example.com");
        entityManager.persist(user);
        entityManager.flush();

        UserProfile profile = new UserProfile(user, "Backend developer");
        entityManager.persist(profile);
        entityManager.flush();

        assertThat(profile.getId()).isEqualTo(user.getId());

        UserProfile loaded =
                entityManager.find(UserProfile.class, user.getId());

        assertThat(loaded.getUser().getId()).isEqualTo(user.getId());
        assertThat(loaded.getBio()).isEqualTo("Backend developer");
    }
}
~~~

The test verifies that the profile's ID equals the user's ID and that the relationship can be read back. `@DataJpaTest` normally runs inside a transaction rolled back after the test, keeping test data temporary.

## 4. Many-to-One: Relationship Supplying Part of a Primary Key

An order has multiple lines; each line is identified by the pair `(order_id, line_number)`:

- `order_id` references the order.
- `line_number` distinguishes lines within the same order.

Here `order_id` is part of the primary key and simultaneously a foreign key. Use `@MapsId("orderId")` to map the relationship into that exact ID component.

### 4.1. Key Class OrderLineId

Create `OrderLineId.java`:

~~~java
package com.example.mapsid;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class OrderLineId implements Serializable {

    @Column(name = "order_id")
    private Long orderId;

    @Column(name = "line_number")
    private Integer lineNumber;

    protected OrderLineId() {
    }

    public OrderLineId(Long orderId, Integer lineNumber) {
        this.orderId = orderId;
        this.lineNumber = lineNumber;
    }

    public Long getOrderId() {
        return orderId;
    }

    public Integer getLineNumber() {
        return lineNumber;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof OrderLineId that)) {
            return false;
        }
        return Objects.equals(orderId, that.orderId)
                && Objects.equals(lineNumber, that.lineNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderId, lineNumber);
    }
}
~~~

The embeddable key class requires a no-arg constructor and must define `equals`/`hashCode` over all key components. This is especially important when the ID is used in collections or caches.

### 4.2. Entity PurchaseOrder

Create `PurchaseOrder.java`:

~~~java
package com.example.mapsid;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    protected PurchaseOrder() {
    }

    public Long getId() {
        return id;
    }
}
~~~

### 4.3. Entity OrderLine with @MapsId("orderId")

Create `OrderLine.java`:

~~~java
package com.example.mapsid;

import jakarta.persistence.Column;
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.MapsId;
import jakarta.persistence.Table;
import java.util.Objects;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @EmbeddedId
    private OrderLineId id;

    @MapsId("orderId")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(nullable = false, length = 80)
    private String sku;

    protected OrderLine() {
    }

    public OrderLine(
            PurchaseOrder order,
            Integer lineNumber,
            String sku) {

        this.order = Objects.requireNonNull(order);
        this.id = new OrderLineId(null, lineNumber);
        this.sku = Objects.requireNonNull(sku);
    }

    public OrderLineId getId() {
        return id;
    }

    public PurchaseOrder getOrder() {
        return order;
    }

    public String getSku() {
        return sku;
    }
}
~~~

`@MapsId("orderId")` references the `orderId` property inside `OrderLineId`. This name must match the Java property name in the ID class, not the column name `order_id`.

When persisting `OrderLine`, JPA extracts `order`'s ID and synchronizes it into `id.orderId`. The `lineNumber` component is still supplied by the application. The table's primary key is the pair `(order_id, line_number)`.

~~~sql
create table order_lines (
    order_id bigint not null,
    line_number integer not null,
    sku varchar(80) not null,
    primary key (order_id, line_number),
    constraint fk_order_line_order
        foreign key (order_id) references purchase_orders(id)
);
~~~

### 4.4. Persisting Orders and Order Lines

~~~java
package com.example.mapsid;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public OrderLineId createOrderWithLine(String sku) {
        PurchaseOrder order = new PurchaseOrder();
        entityManager.persist(order);
        entityManager.flush();

        OrderLine line = new OrderLine(order, 1, sku);
        entityManager.persist(line);
        entityManager.flush();

        return line.getId();
    }
}
~~~

After persisting, the line's key has the form `OrderLineId(orderId = <order ID>, lineNumber = 1)`. The application does not have to assign `orderId` manually because it is mapped from the relationship.

## 5. Distinguishing @MapsId from Ordinary Relationships

A regular `@ManyToOne` relationship only creates a foreign key. The child entity's primary key remains independent:

~~~java
@Entity
@Table(name = "comments")
public class Comment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "post_id", nullable = false)
    private Post post;
}
~~~

In this example, `Comment.id` is the comment's own ID; `post_id` is merely a foreign key. Do not use `@MapsId` because the post's key is not part of the comment's primary key.

| Characteristic | Ordinary Relationship | Relationship with @MapsId |
|---|---|---|
| Child primary key | Independent | Derived wholly or partially from the referenced entity |
| Foreign key | Separate column | Simultaneously mapped into the primary key |
| Example | Comment has its own ID, references Post | UserProfile uses AppUser's ID |
| Multiple children referencing one parent | Possible | Possible if the remaining ID part distinguishes each child |

If the child entity has its own ID and only needs to reference the parent, use an ordinary relationship. Use `@MapsId` when the data model genuinely requires a derived primary key.

## 6. Bidirectional Relationships and the Owning Side

In the One-to-One example, `UserProfile` is the owning side because it contains `@JoinColumn` and the foreign key. If you want to navigate to the profile from `AppUser`, you can add the inverse side:

~~~java
@OneToOne(mappedBy = "user", fetch = FetchType.LAZY)
private UserProfile profile;
~~~

`mappedBy = "user"` points to the `user` relationship property in `UserProfile`. The inverse side does not declare a second `@JoinColumn` and is not where `@MapsId` is placed for this relationship.

In bidirectional relationships, update both sides inside helper methods if the application needs a consistent in-memory object graph. Even when updating both sides of the object graph, the owning side still determines the relationship data written to the database.

## 7. Transactions, Cascades, and Entity Lifecycle

`@MapsId` only describes how identity is mapped; it does not automatically manage the lifecycle of parent and child entities.

1. **Assign the relationship before persisting the dependent entity.** If `user` or `order` is null, JPA has no source from which to populate the mapped ID part.
2. **The parent entity must be managed or validly cascade-persisted.** Referencing a new unpersisted entity without an appropriate cascade can trigger a transient object error from the provider.
3. **Do not assign an independent ID that conflicts with @MapsId.** The relationship is the source of data for the derived key part.
4. **Use a transaction for business operations involving multiple writes.** If creating the parent succeeds but creating the child fails, the transaction must roll back to avoid partial state.
5. **Choose cascades intentionally.** `@MapsId` does not automatically enable `CascadeType.PERSIST` or `CascadeType.REMOVE`. Add cascades only when business lifecycle rules truly require them.
6. **Respect foreign keys and deletion rules.** A dependent child entity usually cannot exist once its parent is deleted; clearly define cascades, deletion order, and database constraints.
7. **Do not use an ID before it is generated.** With auto-increment IDs, the value may only appear after persist/flush depending on strategy and provider.

For a shared-primary-key One-to-One, deleting a user typically requires handling the profile first or applying a cascade suited to your domain model. Never add delete cascades just to make an example pass; consider historical data and retention requirements.

## 8. Common Mapping Errors

| Error | Cause | Solution |
|---|---|---|
| Dependent entity ID remains null | Relationship not assigned or parent lacks an ID yet | Persist parent, assign association, then persist child |
| Unable to persist child entity | Required relationship is null or parent is transient | Ensure valid association and parent persist/cascade |
| Duplicate column mapping error | Mapping foreign key as an independent property alongside ID without MapsId | Use `@MapsId` to model the shared column |
| @MapsId value not recognized | Passed SQL column name instead of Java property name in EmbeddedId | Use exact Java property name, e.g., `@MapsId("orderId")` |
| Composite key fails in Set/Map | Missing or incorrect equals/hashCode | Compare all key components |
| Deleting parent fails | Child entities still reference parent via FK | Handle children first or configure appropriate cascade |
| Relationship updated but ID inconsistent | Reassigned association after entity was managed or had a conflicting ID | Establish relationship before persist; if changing parent, treat as identity change and test thoroughly |

Changing the primary key of an existing entity is a risky operation. For entities using `@MapsId`, changing the parent relationship can effectively change the child entity's primary key. Generally, treat identity-defining relationships as immutable after entity creation; if the business needs to move to a different parent, consider deleting and recreating the dependent entity within a transaction rather than mutating IDs arbitrarily.

## 9. When Should You Use @MapsId?

Use `@MapsId` when:

- The dependent entity has no independent identity outside the parent entity.
- A shared-primary-key One-to-One is a genuine data rule.
- Part of the child entity's composite primary key is the parent entity's key.
- You want JPA to keep the foreign key and primary key values synchronized via a single mapping.
- The domain model clearly expresses that the child entity's lifecycle depends on the parent entity.

Do not use `@MapsId` merely because two entities happen to have matching IDs in an example. If the child entity's ID is generated independently and the relationship is just a regular foreign key, `@ManyToOne` or `@OneToOne` with `@JoinColumn` is sufficient.

## 10. Pre-Implementation Checklist

- [ ] Identified which entity is the parent and which is dependent.
- [ ] Determined whether the relationship maps the entire key or only part of the key.
- [ ] For single keys, used `@MapsId` without arguments.
- [ ] For `@EmbeddedId`, `@MapsId("...")` matches the Java property name.
- [ ] ID attribute type is compatible with the parent entity's primary key type.
- [ ] Column mapping is consistent between `@Id`/`@EmbeddedId` and `@JoinColumn`.
- [ ] Parent entity is persisted or validly cascaded before persisting the dependent entity.
- [ ] Composite key class has an appropriate constructor, equals, and hashCode.
- [ ] Cascades, transactions, and deletion behavior align with business lifecycles.
- [ ] Tests verify ID synchronization and the presence of the foreign key in the database.

`@MapsId` fits best when the relationship between entities is also part of the identity. With shared-primary-key One-to-One, it maps the entire ID from parent to child; with composite keys, it maps a specific component of the embedded key. When ID models, associations, transactions, and lifecycles are designed consistently, JPA can maintain derived keys without requiring manual synchronization of key columns in application code.
