# Sharing Attributes with @MappedSuperclass

In a Spring Data JPA application, many Entities often share the same technical attributes such as primary key, version for concurrency control, creation timestamp, and update timestamp. Repeating these fields and annotations in every Entity leads to duplicated and inconsistent code.

JPA provides @MappedSuperclass to place shared mappings into a parent class. Child Entities inherit those attributes and mappings, while the parent class does not become an independent Entity and does not have its own table. This is a way to reuse mappings via Java inheritance, suitable when child classes share the same persistence structure without needing polymorphic queries through the parent class.

## 1. The Problem of Repeating Attributes Across Entities

Suppose a system has Customer, Product, and Invoice. All three need a primary key, creation timestamp, and version.

If each Entity declares these fields on its own, the source code is duplicated:

~~~java
@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    private Instant createdAt;
}
~~~

~~~java
@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    private Instant createdAt;
}
~~~

Repeating them is not invalid from a JPA standpoint, but when conventions need to change—such as renaming columns, adding callbacks, or adding audit fields—every Entity must be modified. One Entity could be missed or end up with a different mapping from the rest.

Shared mappings can be extracted into a parent class using @MappedSuperclass.

## 2. How Does @MappedSuperclass Work?

@MappedSuperclass marks a Java class whose mappings are inherited by child Entities. JPA reads the annotations on the parent class and applies them to each child Entity's mapping.

Example:

~~~java
import jakarta.persistence.*;
import java.time.Instant;

@MappedSuperclass
public abstract class BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    @Column(nullable = false, updatable = false)
    private Instant createdAt;

    private Instant updatedAt;

    protected BaseEntity() {
    }

    @PrePersist
    protected void beforeInsert() {
        Instant now = Instant.now();
        createdAt = now;
        updatedAt = now;
    }

    @PreUpdate
    protected void beforeUpdate() {
        updatedAt = Instant.now();
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
~~~

Customer Entity:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer extends BaseEntity {

    @Column(nullable = false, length = 150)
    private String fullName;

    protected Customer() {
    }

    public Customer(String fullName) {
        this.fullName = fullName;
    }

    public String getFullName() {
        return fullName;
    }
}
~~~

Product Entity:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product extends BaseEntity {

    @Column(nullable = false, length = 120)
    private String name;

    protected Product() {
    }

    public Product(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
~~~

The id, version, createdAt, and updatedAt mappings are inherited into both Entities. The customers table contains the shared columns along with full_name; the products table contains the shared columns along with name. JPA does not create a base_entity table.

Conceptual model:

~~~text
              BaseEntity
           @MappedSuperclass
       id, version, createdAt,
              updatedAt
                  |
           +------+------+
           |             |
        Customer       Product
         @Entity        @Entity
           |             |
       customers      products
       id              id
       version         version
       created_at      created_at
       updated_at      updated_at
       full_name       name
~~~

Each child Entity remains an independent Entity with its own table and Repository.

## 3. @MappedSuperclass Is Not an Entity

This is the most important difference between a mapped superclass and entity inheritance.

A class annotated with @MappedSuperclass:

- Is not managed as an independent Entity in the persistence context.
- Does not have its own database table merely because it is annotated with @MappedSuperclass.
- Cannot be used directly as the Entity type of a JpaRepository.
- Cannot be the target type of an Entity association such as @ManyToOne or @OneToMany.
- Cannot be queried directly with JPQL as an Entity.

Inappropriate example:

~~~java
public interface BaseEntityRepository
        extends JpaRepository<BaseEntity, Long> {
}
~~~

BaseEntity is not an Entity. Declare Repositories for the child classes instead:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}

public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

If the business domain needs to query all object types through a parent type, or needs associations pointing to the parent type, consider entity inheritance: the parent class is annotated with @Entity and uses an appropriate @Inheritance strategy.

## 4. Inheriting Identifiers and Versions

A mapped superclass can declare an identifier using @Id or @EmbeddedId. Child Entities inherit that identifier mapping.

For example, BaseEntity has:

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

Both Customer and Product inherit the Long id field. Each Entity's Repository uses Long as its ID type:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}

public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

Even though the id attribute is declared in the parent class, it remains the primary key of each child Entity's table. ID values for Customer and Product are managed in separate tables; having the same ID number in both tables does not mean they are the same Entity.

@Version can also be placed in a mapped superclass:

~~~java
@Version
private Long version;
~~~

Hibernate uses version to perform optimistic locking. When a transaction updates an Entity, the provider checks the current version. If another transaction has already updated the record and incremented the version, the stale write may fail with an optimistic locking error.

Do not declare a second identifier in a child class unless using a special mapping supported by JPA. Each Entity must have a clear identifier mapping.

## 5. Inherited Fields and Access Strategy

JPA supports two attribute access strategies:

- **Field access:** mapping annotations are placed on fields.
- **Property access:** mapping annotations are placed on getters.

JPA typically determines the access type based on where the identifier annotation is placed in the hierarchy. If the parent class places @Id on a field, keep field access consistent in the child classes.

Example:

~~~java
import jakarta.persistence.*;

@MappedSuperclass
@Access(AccessType.FIELD)
public abstract class BaseEntity {

    @Id
    private Long id;

    protected BaseEntity() {
    }
}
~~~

Avoid arbitrarily placing some annotations on fields and others on getters. If mixing the two approaches is necessary, specify @Access explicitly at the class or property level according to JPA rules.

Java fields that should not be persisted can be annotated with @Transient. Static or transient fields per persistence rules are also not mapped as regular persistent attributes.

## 6. Overriding Column Names with @AttributeOverride

A mapped superclass can provide default column names. Each child Entity can override the mapping of a basic attribute using @AttributeOverride.

Parent class:

~~~java
import jakarta.persistence.*;
import java.time.Instant;

@MappedSuperclass
public abstract class BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "created_at")
    private Instant createdAt;
}
~~~

Customer renames columns:

~~~java
@Entity
@Table(name = "customers")
@AttributeOverrides({
    @AttributeOverride(
        name = "id",
        column = @Column(name = "customer_id")
    ),
    @AttributeOverride(
        name = "createdAt",
        column = @Column(name = "registered_at")
    )
})
public class Customer extends BaseEntity {

    private String fullName;
}
~~~

Product can keep the default mapping or override individually:

~~~java
@Entity
@Table(name = "products")
@AttributeOverride(
    name = "createdAt",
    column = @Column(name = "created_on")
)
public class Product extends BaseEntity {

    private String name;
}
~~~

In @AttributeOverride:

- name is the inherited Java property name.
- column is the new SQL column mapping.
- Do not use table names or column names in place of the Java property name.
- @AttributeOverrides allows declaring multiple overrides.

Overrides can be used for inherited basic attributes and embedded attributes with the appropriate path. If child Entities do not need differences, keep the mapping in the parent class to avoid redundant configuration.

## 7. Overriding Relationships with @AssociationOverride

A mapped superclass can also declare JPA associations. If child Entities need different join column or join table names, use @AssociationOverride.

Parent class:

~~~java
import jakarta.persistence.*;

@MappedSuperclass
public abstract class OwnedEntity {

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "owner_id")
    private User owner;

    protected OwnedEntity() {
    }

    public User getOwner() {
        return owner;
    }
}
~~~

Customer overrides the join column:

~~~java
@Entity
@Table(name = "customers")
@AssociationOverride(
    name = "owner",
    joinColumns = @JoinColumn(name = "customer_owner_id")
)
public class Customer extends OwnedEntity {

    private String fullName;
}
~~~

@AssociationOverride references the inherited association property name. It can change join columns or the join table depending on the relationship type. The User object in the example must be a real Entity managed by JPA.

A mapped superclass can contain associations to an Entity, but the mapped superclass itself cannot be the target entity of an association.

## 8. Lifecycle Callbacks in a Mapped Superclass

JPA callbacks can be declared in a mapped superclass and applied to child Entities.

~~~java
@MappedSuperclass
public abstract class TimestampedEntity {

    private Instant createdAt;
    private Instant updatedAt;

    @PrePersist
    protected void beforeInsert() {
        Instant now = Instant.now();
        createdAt = now;
        updatedAt = now;
    }

    @PreUpdate
    protected void beforeUpdate() {
        updatedAt = Instant.now();
    }
}
~~~

When a child Entity is persisted, the @PrePersist callback can be invoked. When an Entity is updated through the standard persistence mechanism, @PreUpdate is invoked before the update.

Notes:

- Bulk JPQL updates and native SQL do not trigger per-Entity callbacks like normal dirty checking.
- Callbacks should be short, predictable, and not perform long-running I/O work.
- If multiple classes in the hierarchy declare callbacks, understand JPA callback ordering and avoid duplicate processing.
- Do not treat callbacks as a complete auditing mechanism if the application also writes data via batch jobs or direct SQL.

## 9. Combining with Spring Data JPA Auditing

Spring Data JPA provides auditing to automatically populate the creator and creation/modification timestamps. Audit fields can be placed in a mapped superclass.

~~~java
import jakarta.persistence.EntityListeners;
import jakarta.persistence.MappedSuperclass;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

import java.time.Instant;

@MappedSuperclass
@EntityListeners(AuditingEntityListener.class)
public abstract class AuditableEntity {

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String updatedBy;
}
~~~

Enable auditing:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing
public class JpaAuditingConfiguration {
}
~~~

If you want to record the current user, configure an `AuditorAware<T>` to provide the actor. For example, a web application can retrieve the authenticated username from the Spring Security context.

The @CreatedDate, @LastModifiedDate, @CreatedBy, and @LastModifiedBy annotations belong to Spring Data, not Jakarta Persistence. They require the corresponding listener and auditing configuration.

## 10. Comparing @MappedSuperclass, @Embeddable, and Entity Inheritance

These three mechanisms solve different problems:

| Mechanism | When to Use | Own Table? | Queryable as Entity? |
|---|---|---|---|
| @MappedSuperclass | Sharing mappings via inheritance | No | No |
| @Embeddable + @Embedded | Grouping attributes into a value object | No; columns reside in the owning Entity's table | No |
| Entity inheritance | Modeling an Entity hierarchy with polymorphism | Depends on @Inheritance | Yes |

Example where @Embeddable fits Address or Money:

~~~java
@Embeddable
public class Address {
    private String street;
    private String city;
}
~~~

Entity using composition:

~~~java
@Entity
public class Customer {

    @Id
    private Long id;

    @Embedded
    private Address address;
}
~~~

If the parent class needs to be queried as an Entity or referenced by a JPA association, consider entity inheritance with @Entity and @Inheritance. @MappedSuperclass does not provide that polymorphism.

## 11. When Should You Use @MappedSuperclass?

Suitable when:

- Multiple Entities share id, version, createdAt, updatedAt, or audit fields.
- Each child Entity has its own table.
- There is no need to query the parent class as an Entity.
- Shared mappings have the same meaning and can follow common conventions.

Not suitable when:

- The parent class needs its own Repository.
- A @ManyToOne association needs to point to the parent class.
- JPQL needs to query all child classes via the parent type.
- Child classes have such different data structures that the parent class only retains a few unrelated attributes.
- You want to group values via composition rather than inheritance.

## 12. Common Pitfalls

**Creating a Repository for a mapped superclass**

A mapped superclass is not an Entity. Create a Repository for each child Entity.

**Expecting a parent table**

JPA does not create a separate table for a @MappedSuperclass class. Its attributes are mapped into each child Entity's table.

**Using @Inheritance with a mapped superclass for polymorphic queries**

@Inheritance is for entity inheritance. If you need to query the parent type, switch to a true Entity hierarchy.

**Overriding the wrong property name**

name in @AttributeOverride and @AssociationOverride is the inherited Java property name, not the SQL column name.

**Declaring duplicate identifiers**

If the parent class already declares @Id, the child class should not declare another independent @Id for the same Entity.

**Mixing field access and property access**

Keep the access strategy consistent or use explicit @Access to prevent the provider from reading/writing differently than expected.

**Putting too much business logic in the parent class**

A mapped superclass should contain truly shared attributes and behavior. Customer-specific logic should not be placed in BaseEntity just for reuse.

**Callbacks not running with bulk updates**

JPQL bulk updates and native SQL bypass per-Entity lifecycles. If data is updated that way, handle auditing/versioning manually or use an appropriate workflow.

## 13. Verifying Mappings After Implementation

An integration test should verify:

1. The child Entity is recognized by JPA and can be persisted.
2. Inherited columns appear in the child Entity's table.
3. ID and version are mapped properly.
4. Callbacks or auditing update shared fields as expected.
5. @AttributeOverride generates column names as expected.
6. Inherited associations have the right join columns.
7. Each child Entity's Repository works with the correct ID type.
8. JPQL does not attempt to query the mapped superclass as an Entity.

Beyond tests, inspect the DDL or schema migrations and actual SQL. A successful application startup does not guarantee the running schema matches the intended design.

## 14. Conclusion

@MappedSuperclass is a way to reuse JPA mappings via Java inheritance. It is suited for sharing identifiers, versions, basic attributes, associations, and lifecycle callbacks across multiple Entities that have their own tables. The parent class has no table, is not an independent Entity, and does not support polymorphic queries. Use @AttributeOverride and @AssociationOverride when child Entities need to customize mappings. If you need a value object, choose @Embeddable; if you need a parent class queryable as an Entity, choose entity inheritance.
