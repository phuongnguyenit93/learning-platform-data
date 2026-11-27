# Designing equals and hashCode for Composite Keys

In JPA, a composite primary key is formed from two or more properties. For example, a line item in a purchase order may be identified by the pair of order ID and line number. When representing a composite key with a Java class, that class must implement equals() and hashCode() properly so two key objects holding the same values are treated as the same key.

This implementation affects how Java compares objects, how HashMap/HashSet locate elements, and how JPA recognizes keys. The core rule is: **equals() must compare every component of the key; hashCode() must be computed from those exact same components; key components must remain stable for as long as the object is used as a key.**

## 1. What Is a Composite Key?

A composite primary key is a primary key consisting of multiple columns. A row in a table is only uniquely identified when combining the values of all key components.

Example `order_lines` table:

| order_id | line_number | product_name |
|---:|---:|---|
| 100 | 1 | Keyboard |
| 100 | 2 | Mouse |
| 101 | 1 | Monitor |

In this example, order_id alone is not unique because an order has multiple lines. line_number alone is also not unique because many orders have a line number 1. Only the pair (order_id, line_number) uniquely identifies a row.

The corresponding Java model might be:

~~~java
public class OrderLineKey {
    private Long orderId;
    private Integer lineNumber;
}
~~~

The following two objects must be considered equal if both orderId and lineNumber have the same values:

~~~java
OrderLineKey first = new OrderLineKey(100L, 2);
OrderLineKey second = new OrderLineKey(100L, 2);
~~~

Without overriding equals(), Java defaults to comparing object identity. Because first and second are two distinct objects in memory, the expression first.equals(second) returns false even though their fields share identical values. That contradicts the semantics of a composite key.

## 2. Java's equals() and hashCode() Contract

Any class used as a key in a HashMap or as an element in a HashSet must obey the contracts of Object.equals() and Object.hashCode().

### The equals() Contract

A proper equals() method must satisfy these properties:

1. **Reflexive:** an object must always equal itself.
2. **Symmetric:** if a equals b, then b must also equal a.
3. **Transitive:** if a equals b and b equals c, then a must equal c.
4. **Consistent:** if the data used for comparison does not change, repeated calls must yield the same result.
5. **Non-null:** any non-null object must return false when compared to null.

For a composite key, equality must depend on all key components. If only orderId were compared and lineNumber were ignored, two different line items in the same order would be treated as the same key.

### The hashCode() Contract

hashCode() returns an integer used to group objects into buckets in hash-based structures such as HashMap and HashSet.

Mandatory rules:

- If a.equals(b) is true, then a.hashCode() and b.hashCode() must be equal.
- If two hashCodes are equal, the two objects are not necessarily equal; hash collisions are allowed.
- As long as the fields participating in equals() do not change, hashCode() must remain stable.
- hashCode() should use the exact same set of components as equals().

It is not required for two unequal objects to have different hashCodes. The goal is good distribution and preserving the contract, not producing a globally unique code for every object.

## 3. Implementing with Objects.equals() and Objects.hash()

For a composite key composed of orderId and lineNumber, you can implement it as follows:

~~~java
import java.io.Serializable;
import java.util.Objects;

public class OrderLineKey implements Serializable {

    private Long orderId;
    private Integer lineNumber;

    public OrderLineKey() {
    }

    public OrderLineKey(Long orderId, Integer lineNumber) {
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

        if (!(other instanceof OrderLineKey that)) {
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

Explanation:

- this == other quickly handles the case where two references point to the exact same object.
- instanceof checks whether the other object is of type OrderLineKey.
- Objects.equals(a, b) handles null values safely without throwing a NullPointerException.
- The && operator requires every key component to be equal.
- Objects.hash(...) computes the hash from the exact same two components used in equals().

In Java 17, pattern matching for instanceof allows declaring the variable that directly in the condition. If your project uses an older Java version, write the check and cast separately:

~~~java
if (!(other instanceof OrderLineKey)) {
    return false;
}
OrderLineKey that = (OrderLineKey) other;
~~~

### Why Must All Key Fields Be Compared?

Suppose there are three keys:

~~~java
OrderLineKey a = new OrderLineKey(100L, 1);
OrderLineKey b = new OrderLineKey(100L, 2);
OrderLineKey c = new OrderLineKey(100L, 1);
~~~

The expected results must be:

| Expression | Result |
|---|---|
| a.equals(b) | false |
| a.equals(c) | true |
| a.hashCode() == c.hashCode() | true |
| a.hashCode() == b.hashCode() | Not required to be true or false |

If equals() only checked orderId, a and b would be treated as equal. That is a serious bug because two different lines could be mistaken for the same record.

## 4. Declaring a Composite Key with @EmbeddedId

In JPA, @EmbeddedId places all key components into a separate class annotated with @Embeddable.

Key class:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class OrderLineKey implements Serializable {

    @Column(name = "order_id")
    private Long orderId;

    @Column(name = "line_number")
    private Integer lineNumber;

    public OrderLineKey() {
    }

    public OrderLineKey(Long orderId, Integer lineNumber) {
        this.orderId = Objects.requireNonNull(orderId);
        this.lineNumber = Objects.requireNonNull(lineNumber);
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
        if (!(other instanceof OrderLineKey that)) {
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

Entity using the key:

~~~java
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @EmbeddedId
    private OrderLineKey id;

    private String productName;

    protected OrderLine() {
    }

    public OrderLine(OrderLineKey id, String productName) {
        this.id = id;
        this.productName = productName;
    }

    public OrderLineKey getId() {
        return id;
    }

    public String getProductName() {
        return productName;
    }
}
~~~

Repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderLineRepository
        extends JpaRepository<OrderLine, OrderLineKey> {
}
~~~

When calling findById(), pass an OrderLineKey:

~~~java
OrderLineKey key = new OrderLineKey(100L, 2);

Optional<OrderLine> result =
        orderLineRepository.findById(key);
~~~

Here, equals() and hashCode() belong to the OrderLineKey class. JPA uses this class to represent the primary key value. The OrderLine Entity and the OrderLineKey class serve different roles; do not confuse Entity equals() with key class equals().

## 5. Declaring a Composite Key with @IdClass

@IdClass is an alternative mapping style. Key properties live directly inside the Entity, while the ID class describes the key structure.

ID class:

~~~java
import java.io.Serializable;
import java.util.Objects;

public class OrderLineId implements Serializable {

    private Long orderId;
    private Integer lineNumber;

    public OrderLineId() {
    }

    public OrderLineId(Long orderId, Integer lineNumber) {
        this.orderId = orderId;
        this.lineNumber = lineNumber;
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

Entity:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;

@Entity
@Table(name = "order_lines")
@IdClass(OrderLineId.class)
public class OrderLine {

    @Id
    private Long orderId;

    @Id
    private Integer lineNumber;

    private String productName;

    protected OrderLine() {
    }
}
~~~

Repository:

~~~java
public interface OrderLineRepository
        extends JpaRepository<OrderLine, OrderLineId> {
}
~~~

With @IdClass:

- Property names in the ID class must match the key property names in the Entity.
- Each property's type in the ID class must match the Java type of the corresponding key property in the Entity.
- The ID class's equals() and hashCode() must cover all key components.
- The ID class must satisfy JPA requirements for constructors and serializability.

Both @EmbeddedId and @IdClass require the key class to implement equals() and hashCode(). The main difference is where the key components are placed in the Entity model.

## 6. Comparing @EmbeddedId and @IdClass

| Criterion | @EmbeddedId | @IdClass |
|---|---|---|
| Key components | Grouped inside a single property typed as the key class | Declared as multiple @Id properties on the Entity |
| Key class | Annotated with @Embeddable | Referenced via @IdClass |
| Key access | entity.getId().getOrderId() | entity.getOrderId() |
| Repository generic ID | The @Embeddable class | The ID class declared in @IdClass |
| equals/hashCode | On the @Embeddable class | On the ID class |
| Purpose | Models the key as a value object | Keeps key fields directly on the Entity |

There is no mandatory choice for every project. @EmbeddedId often represents a composite key as a clear value and centralizes key logic in one class. @IdClass fits when you want key properties directly on the Entity. Pick one style per mapping and follow it consistently.

## 7. Why Should Composite Keys Be Stable and Rarely Change?

HashMap and HashSet use hashCode() to determine an element's bucket location. If an object has already been inserted into a HashSet and a field used in computing hashCode() is mutated, the object stays in the old bucket while lookups hash to the new bucket.

Example illustrating the bug when a key class exposes a setter:

~~~java
OrderLineKey key = new OrderLineKey(100L, 1);

Set<OrderLineKey> keys = new HashSet<>();
keys.add(key);

// Suppose there is a setter and a key component is changed:
key.setLineNumber(2);

// May return false because hashCode has changed:
boolean found = keys.contains(key);
~~~

A primary key in a database is also expected to identify a record stably. Mutating key components after an Entity has been saved makes persistence context synchronization, relationship updates, and Entity management complicated or unsupported by the provider.

Design principles:

- Construct keys with complete values from the start.
- Avoid exposing public setters for key components unless strictly necessary.
- Do not modify key components after the Entity has been persisted.
- Do not include descriptive fields like productName, status, or createdAt in the key's equals/hashCode if they do not belong to the primary key.
- If the business needs to change a code, consider using a stable technical key and keeping the business code as a separate property with a unique constraint.

In JPA, providers may require a no-arg constructor and field access per the mapping. Therefore, do not blindly mark all fields final if doing so breaks mapping compatibility. You can keep fields private, provide only a value constructor and getters, and omit setters to discourage application-side mutation.

## 8. Comparing Keys According to Database Semantics

A Java key class must compare values in a way compatible with how the database determines key uniqueness. This is easy to overlook when data types have special comparison semantics.

### Strings and Collations

String.equals() is case-sensitive:

~~~java
"ABC".equals("abc"); // false
~~~

Meanwhile, a database column with a case-insensitive collation may treat these two values as equivalent in comparisons or unique constraints. When the database uses different comparison semantics from Java, normalize key values before saving and enforce consistent normalization everywhere. Do not blindly lowercase if the business code is case-sensitive.

### BigDecimal

BigDecimal.equals() considers both value and scale:

~~~java
new BigDecimal("1.0").equals(new BigDecimal("1.00")); // false
new BigDecimal("1.0").compareTo(new BigDecimal("1.00")) == 0; // true
~~~

Some numeric database types compare these two numeric values as equal. Consequently, using BigDecimal as a key component can cause divergence between Java and the database unless scale is normalized. Ideally avoid decimal numbers as identifying keys; if unavoidable, define and enforce a consistent normalization rule.

### Date/Time and Precision

Databases may store timestamps at lower precision than the original Java value. If a key contains a timestamp, the value after a round-trip may differ from the value before saving. Normalize precision to match the column and database type, or choose a more stable identifier.

### Byte Arrays

Arrays in Java default to identity-based equals. Objects.equals(byteArrayA, byteArrayB) does not compare the contents of two byte arrays either. If a key component genuinely is a byte array, you must use Arrays.equals() and Arrays.hashCode():

~~~java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (!(other instanceof BinaryKey that)) return false;
    return Arrays.equals(value, that.value);
}

@Override
public int hashCode() {
    return Arrays.hashCode(value);
}
~~~

However, using large binary blobs as primary keys is rarely good design. Keys should be small, stable, and easy to compare.

## 9. Do Not Confuse Key Class equals/hashCode with Entity equals/hashCode

A composite key class is a value object: two objects with the same key components represent the same key value. Therefore, the key class's equals/hashCode should compare all key components.

An Entity has a more complex lifecycle:

- A new Entity may not have an ID yet if the ID is auto-generated.
- A persisted Entity receives an ID after saving.
- Hibernate may use proxies to represent lazily loaded Entities.
- Entities have bidirectional relationships, collections, and mutable fields.
- Two Entities with identical business data are not necessarily the same persistent identity.

Do not copy the key class's equals/hashCode implementation verbatim onto an Entity. In particular, never include relationships, collections, or LOBs in an Entity's equals/hashCode because doing so can trigger infinite loops, unintended lazy loading, or shifting hashes.

If a project needs to define equality for Entities, design it separately around your JPA provider's identity and proxy semantics. This lesson focuses on composite key classes, where key components are already clearly defined.

## 10. Can Lombok Generate equals/hashCode?

Lombok supports generating equals/hashCode, provided it is configured accurately. Example:

~~~java
import jakarta.persistence.Embeddable;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Embeddable
@Getter
@NoArgsConstructor
@EqualsAndHashCode(onlyExplicitlyIncluded = true)
public class OrderLineKey {

    @EqualsAndHashCode.Include
    private Long orderId;

    @EqualsAndHashCode.Include
    private Integer lineNumber;
}
~~~

This approach includes only the fields marked with Include in equals/hashCode. Make sure every key component is included and no non-key field slips in.

Be careful with @Data: this annotation generates equals/hashCode over fields by default. If the key class contains extra non-key attributes, or an Entity has relationships, automatic generation can yield unintended equality behavior. For critical composite keys, writing it explicitly or configuring Lombok strictly is usually easier to review.

## 11. Testing equals/hashCode

You can verify the contract with JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.HashSet;
import java.util.Set;
import org.junit.jupiter.api.Test;

class OrderLineKeyTest {

    @Test
    void keysWithSameComponentsAreEqual() {
        OrderLineKey first = new OrderLineKey(100L, 2);
        OrderLineKey second = new OrderLineKey(100L, 2);

        assertEquals(first, second);
        assertEquals(first.hashCode(), second.hashCode());
    }

    @Test
    void differentComponentMakesKeysDifferent() {
        OrderLineKey first = new OrderLineKey(100L, 1);
        OrderLineKey second = new OrderLineKey(100L, 2);

        assertNotEquals(first, second);
    }

    @Test
    void equalKeyCanBeFoundInHashSet() {
        OrderLineKey stored = new OrderLineKey(100L, 2);
        OrderLineKey lookup = new OrderLineKey(100L, 2);

        Set<OrderLineKey> keys = new HashSet<>();
        keys.add(stored);

        assertTrue(keys.contains(lookup));
        assertEquals(1, keys.size());
    }

    @Test
    void keyIsNotEqualToNullOrAnotherType() {
        OrderLineKey key = new OrderLineKey(100L, 2);

        assertNotEquals(null, key);
        assertNotEquals("100-2", key);
    }
}
~~~

These tests verify the main cases:

- Two independent instances with identical key components must be equal.
- Two keys differing in one component must not be equal.
- A HashSet must find an instance equivalent to the one inserted.
- A key must never equal null or an object of a different type.

You can also add checks for symmetry, transitivity, and consistency:

~~~java
OrderLineKey a = new OrderLineKey(100L, 2);
OrderLineKey b = new OrderLineKey(100L, 2);
OrderLineKey c = new OrderLineKey(100L, 2);

assertTrue(a.equals(b));
assertTrue(b.equals(a));
assertTrue(b.equals(c));
assertTrue(a.equals(c));
assertTrue(a.equals(a));
~~~

In addition to unit tests, write integration tests that save an Entity with a composite key to the database and look it up again using a new key instance with the same values. That confirms JPA mapping, schema, and provider composite key handling all work together properly.

## 12. Checklist for Reviewing a Composite Key Class

When reviewing an ID class, verify:

1. The class is properly used with @EmbeddedId or @IdClass.
2. The key class contains the exact and complete set of key components.
3. Field names and types match the Entity mapping as required by the chosen annotation style.
4. A suitable no-arg constructor exists and meets JPA requirements.
5. The key class satisfies the Serializable requirement of traditional composite key models.
6. equals() compares all key components and excludes non-key fields.
7. hashCode() uses the exact same components used in equals().
8. Key values are not mutated after being placed in a HashMap/HashSet or after the Entity is persisted.
9. Java comparison semantics match the database's data types, collations, and precision.
10. Unit tests and integration tests cover equality, inequality, and database round-trips.

## 13. Conclusion

A composite key is an identifier value made up of multiple components. equals() must compare all key components, and hashCode() must be computed from those exact same components to honor Java's contract. In JPA, this rule is implemented on the key class used with @EmbeddedId or @IdClass. Designing stable keys free of non-key fields, aligned with database comparison semantics, and verified with HashSet and integration tests makes Entity management far more reliable.
