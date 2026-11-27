# Designing equals, hashCode, toString, and Using Lombok Safely with Entities

JPA entities are objects with a persistence lifecycle: they can be newly created, managed, flushed, detached, or loaded through a proxy. Therefore, equals(), hashCode(), and toString() must be designed around entity identity and lifecycle. Auto-generation approaches suitable for DTOs or value objects can cause bugs when applied verbatim to entities, especially with database-generated primary keys, bidirectional relationships, and lazy loading.

This lesson explains Java's equality contract, the difference between object identity and entity identity, how to choose a comparison key, the impact of HashSet/HashMap, Hibernate proxies, recursion and lazy loading in toString(), and controlled Lombok usage. Examples use Customer, Student, and Order for illustration.

## 1. What roles do these three methods play?

Java provides three fundamental methods from Object:

- **equals(Object)** determines when two objects are considered logically equal.
- **hashCode()** produces the hash value used by HashSet, HashMap, and hash-based data structures.
- **toString()** produces a string representation for debugging, logging, or displaying information.

By default, Object.equals() compares reference identity: two variables are equal only if they reference the exact same object in memory. Object.hashCode() is also tied to object identity per Java's contract; it must not be mistaken for a database ID.

With JPA entities, two different Java objects can represent the same database row. For instance, a Customer loaded in one persistence context and the same Customer loaded in another persistence context. Both objects can share the same primary key yet be distinct references.

You must decide which notion of equality your domain requires: same object, same database entity, or same business value. There is no single implementation that is right for every entity.

## 2. The equals() and hashCode() contract

Java requires equals() to satisfy these properties:

1. **Reflexive**: an object must equal itself.
2. **Symmetric**: if a.equals(b) is true, then b.equals(a) must also be true.
3. **Transitive**: if a equals b and b equals c, then a must equal c.
4. **Consistent**: the result must remain stable as long as information used in comparisons does not change.
5. **Non-null**: a.equals(null) must be false.

The hashCode() contract:

- If two objects are equal according to equals(), they must have the same hashCode().
- Two unequal objects may have the same hashCode(); collisions are allowed.
- While information used in equals() does not change, hashCode() must remain constant throughout the object's usage in the application.

The first rule is crucial for entities: you must not write equals() comparing ID while hashCode() is based on name or address. Two equal objects must produce identical hash codes.

## 3. Object identity vs. entity identity

Consider two cases:

~~~java
Customer first = entityManager.find(Customer.class, 10L);
Customer second = anotherEntityManager.find(Customer.class, 10L);
~~~

If both queries return the same row, first and second may be two separate Java objects both representing the Customer with ID 10.

Within the same persistence context, JPA maintains managed entity identity: the same entity type and primary key are normally represented by the same managed instance in that context. When moving to another persistence context or reading a detached entity, you can encounter a different object representing the same row.

This affects:

- Comparing entities across two transactions.
- Using entities in a Set or as Map keys.
- Merging data from multiple repositories or persistence contexts.
- Checking relationships in the domain.
- Handling entities after serialization/deserialization or across API layers.

Before overriding equals(), determine whether your application truly needs equality by entity identity or only needs same-instance comparison within a transaction. If there is no need to compare two distinct instances, keeping Object's default implementation can be the simplest and safest choice.

## 4. Choosing an equality strategy for entities

There are three common strategies.

### 4.1. Keeping default equality by object identity

Do not override equals() and hashCode(). Two references are equal only when they point to the exact same object.

Suitable when:

- The entity is primarily used within a single persistence context.
- The application does not need to compare detached instances with managed instances.
- Relationships are handled via IDs or repository queries.
- Deduplicating entities in a Set by ID is not needed.

The advantage is avoiding unassigned IDs, proxies, or mutable business keys. The limitation is that two objects representing the same database row are still not equal according to equals().

### 4.2. Equality based on primary key

Two entities of the same type are considered equal when both already have the same non-null primary key.

Key rules:

- If both objects are the same reference, return true.
- If either lacks an ID, two distinct references must not be considered equal.
- If both have IDs, compare IDs after verifying the same entity type.
- hashCode must remain stable before and after the database assigns the ID.

This approach fits when the ID is the entity's identifier and the application needs to compare instances representing the same row.

### 4.3. Equality based on a natural/business key

Two entities are equal when a stable business key matches, such as an ISO country code or a uniquely defined product code.

A key used for equality must be:

- Assigned as soon as the object is created.
- Immutable throughout the entity's lifecycle.
- Unique within the business scope.
- Independent of relationships or collections.
- Subject to clear normalization rules, such as casing or whitespace.

Email may not be a good natural key if users are allowed to change their email. Display names, addresses, or statuses are also typically mutable data and should not be used as equality keys.

When using a business key, the database still needs a UNIQUE constraint to protect uniqueness against concurrent transactions.

## 5. Special issue with database-generated IDs

Suppose a new entity does not yet have an ID:

~~~java
Customer customer = new Customer("An");
Set<Customer> customers = new HashSet<>();

customers.add(customer);
entityManager.persist(customer);
entityManager.flush();
~~~

The database may assign the ID during persist or flush, depending on the ID generation strategy. If hashCode() depends directly on the ID, the hash value can change after the object has already been placed into the HashSet.

HashSet selects a bucket based on hashCode at the moment of add. When hashCode changes, calls to contains() or remove() may fail to locate the object in its original bucket:

~~~java
customers.contains(customer); // May return false if hashCode changed.
~~~

This is a real bug, even though the object is still inside the Set.

There are two ways to solve this:

- Use an immutable business key, available from entity creation, for both equals() and hashCode().
- If equality is based on a generated ID, use a hashCode that is constant per entity class rather than based on the ID value.

Never use a null ID as a shared value to conclude two new entities are equal. Two new unsaved Customers are two distinct entities even though both have id = null.

## 6. Example of generated-ID equality accounting for Hibernate proxies

With Hibernate, an entity may be represented by a proxy class to support lazy loading. Comparing getClass() directly between a real entity and a proxy can yield false because the proxy is a runtime-generated subclass.

The example below uses Hibernate's API to retrieve the proxy's persistent class without initializing the proxy just to determine its class:

~~~java
package example.domain;

import jakarta.persistence.*;
import org.hibernate.proxy.HibernateProxy;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    private static Class<?> persistentClass(Object entity) {
        if (entity instanceof HibernateProxy proxy) {
            return proxy.getHibernateLazyInitializer()
                .getPersistentClass();
        }
        return entity.getClass();
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }

        if (other == null
                || persistentClass(this) != persistentClass(other)) {
            return false;
        }

        Customer that = (Customer) other;
        return id != null && id.equals(that.getId());
    }

    @Override
    public int hashCode() {
        return persistentClass(this).hashCode();
    }
}
~~~

Explanation:

- this == other handles the same-object case, even when the entity is still transient with a null ID.
- persistentClass() retrieves the actual entity class if the object is a Hibernate proxy.
- Two distinct objects are equal only when they share the same persistent class and a non-null matching ID.
- hashCode() depends solely on the persistent class, so it never changes when the ID is assigned.

This implementation depends on Hibernate. If using another JPA provider, replace the proxy detection with that provider's API or choose an equality strategy suited to your environment. If using entity inheritance, clarify whether subclasses count as the same equality type; the example above requires an exact persistent class match.

Class-based hash codes cause collisions among many entities of the same type. That still obeys the Java contract, though it can degrade HashSet/HashMap performance if a single collection holds a very large number of entities of the same class. When an immutable business key exists, equality and hashCode by business key usually give better distribution.

## 7. Why not use all entity fields in equals()?

A common implementation compares every field:

~~~java
return Objects.equals(name, that.name)
    && Objects.equals(email, that.email)
    && Objects.equals(orders, that.orders);
~~~

This approach has several issues:

- Changing name or email changes equality.
- Relationship collections may be lazily loaded when equals() runs.
- Comparing two entities can trigger numerous database queries.
- Bidirectional relationships can cause infinite recursion.
- Collections can mutate while the object sits in a HashSet.
- Two entities with different IDs but identical current data may be treated as the same object.

Entities have their own identity and lifecycle. Business fields often change over time; therefore, all fields should not be used for equality.

Avoid including in equals()/hashCode():

- Relationship collections such as List, Set, Map.
- `@OneToMany`, `@ManyToMany`, and other associations.
- Mutable fields such as name, address, status, or balance.
- Potentially lazy-loaded fields.
- Technical fields that change over time such as updatedAt or version.

## 8. How is Lombok @Data dangerous for Entities?

Lombok `@Data` is a composite annotation, equivalent to asking Lombok to generate:

- `@Getter` for fields.
- `@Setter` for non-final fields.
- `@RequiredArgsConstructor`.
- `@ToString`.
- `@EqualsAndHashCode`.

For simple DTOs, this can be convenient. For JPA entities, the auto-generated methods may include all fields, including relationships and collections.

Example:

~~~java
@Data
@Entity
public class Student {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @ManyToMany
    private Set<Course> courses = new HashSet<>();
}
~~~

This code can cause several problems:

1. equals() and hashCode() include id, name, and courses in equality. When name or the collection changes, hashCode can change.
2. equals() can traverse lazy relationships and trigger database queries.
3. Student.toString() can print courses; Course.toString() in turn prints students, creating infinite recursion.
4. toString() can load batches of entities just to write a log line.
5. Auto-generated setters for ID and collections allow code to arbitrarily mutate persistence state.
6. Lombok-generated constructors may fail to provide the no-arg constructor JPA needs if annotations are combined carelessly.

Do not use `@Data` on entities with persistence relationships. Choose individual annotations according to purpose.

## 9. Using Lombok safely for getters, constructors, and toString

You can use Lombok to reduce boilerplate while keeping fields under control:

~~~java
package example.domain;

import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.ToString;

import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "students")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@ToString(
    onlyExplicitlyIncluded = true,
    doNotUseGetters = true
)
public class Student {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @ToString.Include
    private Long id;

    @Column(nullable = false, length = 120)
    @ToString.Include
    private String name;

    @OneToMany(mappedBy = "student", fetch = FetchType.LAZY)
    @ToString.Exclude
    private List<Enrollment> enrollments = new ArrayList<>();

    public Student(String name) {
        this.name = name;
    }

    public void rename(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Name is required");
        }
        this.name = name;
    }
}
~~~

Here:

- `@Getter` generates getters for the fields.
- `@NoArgsConstructor(access = AccessLevel.PROTECTED)` generates a no-arg constructor with visibility suited for JPA.
- No blanket public setters are generated; state changes go through business methods like `rename()`.
- `@ToString(onlyExplicitlyIncluded = true)` prints only fields marked `@ToString.Include`.
- `doNotUseGetters = true` instructs Lombok to read fields directly in `toString()`.
- The `enrollments` relationship is excluded from the string representation.

Because `onlyExplicitlyIncluded` is enabled, relationships not marked Include will not appear. `@ToString.Exclude` still communicates intent clearly in case annotations are changed later.

Only include safe data in `toString()`. Do not print passwords, tokens, secrets, sensitive personal information, or large payloads. `toString()` is for debugging; it is not an API serialization format.

## 10. Using Lombok for equals/hashCode with an immutable natural key

If an entity has a genuinely stable business key, Lombok can generate equals/hashCode from only the specified field.

Example Country with a two-letter ISO code:

~~~java
package example.domain;

import jakarta.persistence.*;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.AccessLevel;
import lombok.ToString;

@Entity
@Table(name = "countries")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@EqualsAndHashCode(onlyExplicitlyIncluded = true)
@ToString(onlyExplicitlyIncluded = true, doNotUseGetters = true)
public class Country {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "iso_code", nullable = false, unique = true,
            updatable = false, length = 2)
    @EqualsAndHashCode.Include
    @ToString.Include
    private String isoCode;

    @Column(nullable = false, length = 100)
    @ToString.Include
    private String name;

    public Country(String isoCode, String name) {
        if (isoCode == null || !isoCode.matches("[A-Z]{2}")) {
            throw new IllegalArgumentException("Invalid ISO code");
        }
        this.isoCode = isoCode;
        this.name = name;
    }
}
~~~

Lombok only includes isoCode in equals/hashCode because the field is marked `@EqualsAndHashCode.Include` and the class enables `onlyExplicitlyIncluded`. ID, name, and relationships do not participate in equality.

Conditions for this approach to be safe:

- isoCode is set as soon as the object is created.
- isoCode does not change after the object is used in collections.
- The database has a unique constraint.
- Code normalization rules are applied consistently.
- Equality is tested with proxies and inheritance if the application uses Hibernate proxies or entity hierarchies.

If the business key can be null or change, do not use this approach. For entities using generated IDs, prefer a deliberate equals/hashCode implementation as shown in the previous section.

## 11. Lombok @EqualsAndHashCode.Include and Exclude

Lombok offers two ways to control fields:

~~~java
@EqualsAndHashCode(onlyExplicitlyIncluded = true)
class Example {
    @EqualsAndHashCode.Include
    private String immutableCode;

    private String mutableName;

    @EqualsAndHashCode.Exclude
    private Set<RelatedEntity> relations;
}
~~~

- `onlyExplicitlyIncluded = true` ensures no field participates unless marked Include.
- `@EqualsAndHashCode.Include` adds the selected field or method to equality.
- `@EqualsAndHashCode.Exclude` excludes a field from equality under default configuration.

For entities, `onlyExplicitlyIncluded` is usually easier to review because newly added fields will not automatically participate in equality.

However, this annotation does not by itself solve every proxy issue. Lombok has a `canEqual()` mechanism to handle some inheritance cases, yet you still need to check proxy classes, access strategies, and how getters are invoked. For entities using generated IDs or complex inheritance, a manual implementation usually offers clearer control.

Do not use `callSuper = true` mechanically. If the superclass contains an ID, mutable state, or collections, child entity equality can be affected unintentionally. Only use it when the superclass is truly a stable identifying part of the domain and the inheritance model is designed for equality.

## 12. Constructors, Builders, and setters generated by Lombok

A JPA entity must satisfy the constructor and proxy requirements of the JPA provider. For standard entities:

- The entity needs a no-arg constructor with public or protected visibility.
- The entity class should not be final.
- Persistent fields and methods that the provider must access should not be final if the provider needs proxies/subclasses.
- Avoid `@Value` for standard entities because it makes the class/fields final and targets immutable value objects.
- If using `@Builder`, declare a separate no-arg constructor to guarantee JPA has the constructor it needs.
- Avoid builders for entities with many required relationships if they allow creating objects in invalid states.
- Avoid public setters for ID, version, and associations if mutating those fields is not permitted by business rules.

Example combining Builder in a controlled way:

~~~java
@Entity
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, updatable = false)
    private String sku;

    @Column(nullable = false)
    private String name;

    public Product(String sku, String name) {
        this.sku = Objects.requireNonNull(sku);
        this.name = Objects.requireNonNull(name);
    }

    public static Product create(String sku, String name) {
        return new Product(sku, name);
    }
}
~~~

This example uses a factory method instead of letting a builder assign every field. If a project genuinely needs a builder, restrict the builder to valid input properties and keep the JPA constructor separate.

## 13. toString() and lazy loading

An entity may have a lazy relationship:

~~~java
@OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
private List<Order> orders;
~~~

If `toString()` prints `orders`, when calling:

~~~java
log.debug("Customer: {}", customer);
~~~

Hibernate may need to load the collection. That leads to:

- Unexpected database queries when logging.
- N+1 queries if logging inside a loop.
- LazyInitializationException if the persistence context has closed.
- Infinite recursion if `Order.toString()` in turn prints `Customer`.
- Overly large logs when the collection has many elements.

How to handle it:

- Do not include associations in `toString()`.
- Use `onlyExplicitlyIncluded` and include only small, safe scalar fields.
- If you need to log relationships, log a known ID or a count already computed inside the transaction.
- Do not call `toString()` to serialize an entity to JSON; use DTOs and explicitly configured serializers.
- Do not use Lombok `@Data` on entities with relationships.

`toString()` should be fast, bounded, and never trigger unexpected queries.

## 14. Testing equals/hashCode for entities

Do not test just one simple pair of objects. Test states across the lifecycle.

### 14.1. Testing basic properties

These are illustrative test methods; place them in a JUnit 5 test class with appropriate imports and test configuration:

~~~java
@Test
void equalsIsReflexiveAndNullSafe() {
    Customer customer = new Customer("An");

    assertEquals(customer, customer);
    assertNotEquals(customer, null);
}

@Test
void twoTransientEntitiesAreNotEqual() {
    Customer first = new Customer("An");
    Customer second = new Customer("An");

    assertNotEquals(first, second);
}
~~~

The test above matches the generated-ID strategy: two transient entities with different references and no ID yet must not be considered equal.

### 14.2. Testing HashSet before and after persist

~~~java
@Test
void hashCodeRemainsStableAfterGeneratedIdIsAssigned() {
    Customer customer = new Customer("An");
    Set<Customer> customers = new HashSet<>();

    customers.add(customer);

    entityManager.persist(customer);
    entityManager.flush();

    assertTrue(customers.contains(customer));
}
~~~

This test catches the bug where hashCode changes after the ID is assigned by the database.

### 14.3. Testing two instances representing the same row

~~~java
@Test
void detachedAndReloadedInstancesCompareByIdentity() {
    Customer customer = new Customer("An");
    entityManager.persist(customer);
    entityManager.flush();

    Long id = customer.getId();
    entityManager.clear();

    Customer reloaded = entityManager.find(Customer.class, id);

    assertNotSame(customer, reloaded);
    assertEquals(customer, reloaded);
    assertEquals(customer.hashCode(), reloaded.hashCode());
}
~~~

In a real test, after `clear()` the `customer` object is detached; `reloaded` is a new instance in the current persistence context. The test verifies ID-based equality.

### 14.4. Testing proxies and toString

With Hibernate, add tests for:

- Comparing a loaded entity with a proxy obtained via `getReference()`.
- Testing both directions: `entity.equals(proxy)` and `proxy.equals(entity)`.
- Verifying that the hashCode of the proxy and real entity are compatible.
- Verifying that `toString()` does not traverse relationship collections.
- Verifying that logging/`toString()` does not trigger unexpected SQL when proxies are uninitialized.

SQL verification can use Hibernate statistics or a datasource query counter in integration tests. Do not rely solely on the test not throwing an exception.

## 15. Common pitfalls

**1. Using a null ID to compare two new entities**

Two distinct transient entities both have a null ID. Never conclude they are equal merely because null equals null.

**2. hashCode() changing after persist**

If hashCode depends on a generated ID, an object already placed in a HashSet may no longer be found after the ID is assigned. Use an immutable business key or a stable hashCode per entity class.

**3. Comparing getClass() directly against a Hibernate proxy**

A proxy may be a subclass of the entity. Direct class comparison can cause an entity and a proxy for the same row to be treated as unequal. Choose proxy handling suited to the provider.

**4. Using all fields in equals/hashCode**

Mutable fields and relationships cause equality to shift, triggering lazy queries and recursion. Use only stable identifiers.

**5. Using @Data on entities**

`@EqualsAndHashCode` and `@ToString` get generated over too many fields; setters can also allow arbitrary mutation of IDs or relationships. Choose individual Lombok annotations.

**6. Printing relationship collections in toString()**

This can trigger lazy loading, N+1 queries, and recursion. Include only controlled scalar fields.

**7. Using @Value or final entities**

Final structures are incompatible with many proxy mechanisms and standard JPA entity requirements. Use entity classes that the provider can manage and proxy.

**8. Using a mutable business key**

If email or name can change while participating in hashCode, the object can lose its slot in a HashSet. Only use immutable natural keys.

**9. Forgetting to check inheritance**

Parent and child entities may share a numeric ID without necessarily being the same entity type. Equality must reflect inheritance policy and persistent type.

## 16. Selection and implementation workflow

When creating a new entity, decide in order:

1. Determine whether two instances across different persistence contexts need to be compared.
2. If not needed, consider keeping default equals/hashCode.
3. If needed, decide whether entity identity is based on a generated ID or an immutable business key.
4. If using a generated ID, handle null IDs and keep hashCode stable after persist.
5. If using Hibernate proxies, check the persistent class instead of comparing proxy classes directly.
6. Do not include collections, associations, or mutable fields in equality.
7. Write `toString()` with only safe scalar fields.
8. Use Lombok selectively for getters, constructors, and `toString`; avoid `@Data`.
9. Test transient, persisted, detached, proxy, and HashSet cases.
10. Review again whenever changing entity inheritance, primary keys, or business keys.

## 17. Self-assessment checklist

- [ ] I can explain the equals() and hashCode() contract.
- [ ] I can distinguish object identity from entity identity.
- [ ] I understand why null IDs cannot establish equality between two transient entities.
- [ ] I know that hashCode based on a generated ID can break HashSet after persist.
- [ ] I can choose among default identity, generated ID, and immutable business key.
- [ ] I understand the impact of Hibernate proxies on getClass().
- [ ] I do not include associations or collections in equals/hashCode.
- [ ] I understand why @Data is dangerous for entities.
- [ ] I use @Getter, constructors, and @ToString selectively.
- [ ] I exclude lazy relationships and sensitive data from toString().
- [ ] I avoid @Value and final classes for standard JPA entities.
- [ ] I have tests for HashSet before/after persist and tests for proxies.
- [ ] I have defined equality behavior for entity inheritance.

## 18. Review questions

**1. Why might two entities with the same ID not be the same Java object?**

Because they may have been loaded in different persistence contexts or at different times. Each context can create a separate instance representing the same database row.

**2. Why should you not compare two transient entities solely by ID?**

Because both usually have a null ID. Comparing null with null would cause two unrelated new objects to be treated as equal.

**3. Why can hashCode based on a generated ID cause bugs with HashSet?**

Because the ID is assigned after the object has already been added to the Set. Changing hashCode leaves the object in the old bucket while lookups search the new bucket.

**4. Why is @Data unsuitable for entities with relationships?**

Because Lombok generates equals/hashCode and toString from many fields, which can drag in lazy relationships, recursion, mutable fields, and unexpected hash changes.

**5. Should @OneToMany collections be included in toString()?**

No. Collections can be lazy, very large, and link back to the current entity. Printing collections can cause unexpected queries, N+1 issues, or infinite recursion.

**6. When can Lombok @EqualsAndHashCode be safe?**

When including only an immutable, non-null, unique, and consistently normalized business key; while also verifying provider proxies and inheritance. For generated IDs, write equality manually to control lifecycle behavior.

**7. When should default equals/hashCode be kept?**

When the application only needs object identity within one persistence context and does not need to compare detached instances representing the same row. This is a valid choice that avoids unnecessary complexity.

Designing equality properly helps entities behave reliably across transient, managed, and detached states. Using Lombok selectively reduces boilerplate while preserving control over identity, lazy loading, and the persistence lifecycle.