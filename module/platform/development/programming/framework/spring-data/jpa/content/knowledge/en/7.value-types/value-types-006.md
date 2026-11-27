# Converting Data with AttributeConverter and @Convert

JPA maps entity Java attributes to database columns. Normally, providers like Hibernate already know how to store basic types such as String, Integer, BigDecimal, LocalDate, and enums using default rules. However, an application sometimes uses a custom Java type to represent a business value while the database needs to store a simpler type. JPA provides **AttributeConverter** to convert between these two representations at the persistence boundary.

This lesson explains the AttributeConverter contract, how to write a converter, how to attach a converter with @Convert, how to use autoApply, how to apply it to embedded attributes and collections, and important limitations to keep in mind. The main example uses the OrderStatus enum in Java and stores short codes in a VARCHAR/CHAR column.

## 1. Why Do We Need AttributeConverter?

Suppose an application represents order status with an enum:

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
~~~

If using @Enumerated(EnumType.STRING), the database stores the strings NEW, PAID, and CANCELLED. This is readable, but the enum names become part of the stored data. If a constant is renamed in Java, old data may no longer match.

If using @Enumerated(EnumType.ORDINAL), the database stores ordinal numbers 0, 1, 2. This is shorter but risky when constants are added or reordered: a value's ordinal can shift and old data gets misinterpreted.

In a business system, the database may need to store stable codes:

| Java value | Code stored in database |
|---|---|
| NEW | N |
| PAID | P |
| CANCELLED | C |

We want Java code to keep working with OrderStatus while the database only stores the code. AttributeConverter performs the conversion:

~~~text
OrderStatus.NEW
      |
      | convertToDatabaseColumn(...)
      v
     "N"
      |
      v
VARCHAR / CHAR column

VARCHAR / CHAR column
      |
      | convertToEntityAttribute(...)
      v
     "N"
      |
      v
OrderStatus.NEW
~~~

A converter decouples the domain representation from the storage representation. It is especially useful for enums with business codes, value objects, monetary types with custom rules, or legacy data whose format differs from the Java type.

## 2. The AttributeConverter Contract

Jakarta Persistence defines the generic interface:

~~~java
public interface AttributeConverter<X, Y> {
    Y convertToDatabaseColumn(X attribute);
    X convertToEntityAttribute(Y dbData);
}
~~~

The two type parameters have specific meanings:

- **X** is the attribute type in the entity or embeddable—the Java type used by business code.
- **Y** is the corresponding database representation type, usually a basic type supported by the JPA provider and JDBC driver.

The two methods convert in opposite directions:

| Method | Conversion direction | When it is used |
|---|---|---|
| convertToDatabaseColumn(X) | Java → database | When writing or synchronizing the attribute value to the database |
| convertToEntityAttribute(Y) | database → Java | When reading the column value to construct or populate an entity |

Example with enum:

- Java OrderStatus.PAID is converted to the string "P" before saving.
- The string "P" read from the database is converted back to OrderStatus.PAID.

A converter only handles attribute values. It does not replace entities, repositories, transactions, or relationship mappings. Nor does it automatically create tables, columns, foreign keys, or migrations.

## 3. Writing a Converter for an Enum

First, define an enum with stable database codes:

~~~java
package example.domain;

public enum OrderStatus {
    NEW("N"),
    PAID("P"),
    CANCELLED("C");

    private final String databaseCode;

    OrderStatus(String databaseCode) {
        this.databaseCode = databaseCode;
    }

    public String databaseCode() {
        return databaseCode;
    }

    public static OrderStatus fromDatabaseCode(String code) {
        return switch (code) {
            case "N" -> NEW;
            case "P" -> PAID;
            case "C" -> CANCELLED;
            default -> throw new IllegalArgumentException(
                "Unknown order status code: " + code
            );
        };
    }
}
~~~

Each enum constant holds the code used for storage. The fromDatabaseCode() method converts a code read from the database into the corresponding enum. Invalid values raise a clear error so bad data is not silently turned into another status.

Next, create the converter:

~~~java
package example.persistence;

import example.domain.OrderStatus;
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = false)
public class OrderStatusConverter
        implements AttributeConverter<OrderStatus, String> {

    @Override
    public String convertToDatabaseColumn(OrderStatus attribute) {
        return attribute == null ? null : attribute.databaseCode();
    }

    @Override
    public OrderStatus convertToEntityAttribute(String dbData) {
        return dbData == null
            ? null
            : OrderStatus.fromDatabaseCode(dbData);
    }
}
~~~

Explanation:

- **@Converter** marks the class as a JPA converter so the provider discovers and uses it.
- **autoApply = false** means the converter is only applied where explicitly declared.
- **AttributeConverter<OrderStatus, String>** indicates the Java attribute is OrderStatus and the database value is String.
- **convertToDatabaseColumn()** returns the code N, P, or C.
- **convertToEntityAttribute()** restores the enum from the database code.

Both methods handle null so they do not invoke methods on a null value. For attributes declared NOT NULL, validation and constraints still belong at the appropriate layers; a converter does not replace database constraints.

Avoid returning a default status when encountering an unknown code. If the database contains an invalid value, throwing a clear error helps detect legacy data or a missing migration. If the system needs backward compatibility during a rollout phase, explicitly define and test the policy for legacy codes.

## 4. Attaching a Converter with @Convert

Create an entity using the converter:

~~~java
package example.domain;

import example.persistence.OrderStatusConverter;
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
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

    @Column(name = "status_code", nullable = false, length = 1)
    @Convert(converter = OrderStatusConverter.class)
    private OrderStatus status;

    protected PurchaseOrder() {
        // Constructor for JPA.
    }

    public PurchaseOrder(OrderStatus status) {
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }
}
~~~

Key points:

- @Convert specifies the converter applied to the status attribute.
- @Column describes the column name and constraints.
- The Java type of the field remains OrderStatus.
- The value stored via the converter is a String, not an ordinal or enum name.

With this mapping, the status_code column can be declared as CHAR(1) or VARCHAR(1), depending on the DBMS and project schema. Example SQL:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    status_code CHAR(1) NOT NULL,
    CONSTRAINT chk_purchase_orders_status
        CHECK (status_code IN ('N', 'P', 'C'))
);
~~~

Identity column syntax varies across databases. The DDL above illustrates the structure; use syntax suited for PostgreSQL, MySQL, H2, or the running DBMS. The CHECK constraint in the database protects the set of valid codes even when data is written from another application.

## 5. @Converter(autoApply = true)

If a converter fits every attribute of the same Java type within the persistence unit, autoApply can be enabled:

~~~java
@Converter(autoApply = true)
public class OrderStatusConverter
        implements AttributeConverter<OrderStatus, String> {
    // The two conversion methods remain the same as in the previous example.
}
~~~

When autoApply = true, the JPA provider automatically applies the converter to mapped attributes of type OrderStatus in the persistence unit. The entity then does not need @Convert on the field:

~~~java
@Column(name = "status_code", nullable = false, length = 1)
private OrderStatus status;
~~~

Only use autoApply when the same Java type always has the same storage rule. If an enum is stored as codes N/P/C in one table but as full strings in another, autoApply is too broad; use an explicit converter on each attribute instead.

Do not declare multiple auto-apply converters targeting the same attribute type in the same persistence unit. If the provider cannot determine a single matching converter, the mapping metadata may be invalid.

### 5.1. Disabling auto-apply for an attribute

If an auto-apply converter is active but one attribute needs to keep a different mapping, you can use:

~~~java
@Convert(disableConversion = true)
private OrderStatus status;
~~~

This instructs the provider not to apply automatic converters to that attribute. Use only after determining the desired storage type and verifying the corresponding database mapping.

### 5.2. Choosing explicit vs. auto-apply

| Criterion | Explicit @Convert | autoApply = true |
|---|---|---|
| Scope | One attribute or specified scope | Matching mapped attributes in the persistence unit |
| Clarity | Looking at the entity shows which converter is used | Need to find the global converter to understand the mapping |
| Reusability | Repeat the annotation on fields that need it | Automatically applied across many entities |
| Best when | Rules differ per column or entity | One Java type has one consistent storage rule |
| Risk | Forgetting to attach @Convert on a new field | Unintended impact on fields of the same type |

For business-critical data, favor rules that are easy to read and inspect. Auto-apply reduces annotations but widens the blast radius.

## 6. Cases Where JPA Does Not Apply Converters

AttributeConverter is designed for basic attributes. According to Jakarta Persistence rules, converters are not applied to the following cases:

- Primary key attributes mapped with @Id.
- Version attributes mapped with @Version.
- Relationship attributes mapped with @OneToOne, @OneToMany, @ManyToOne, or @ManyToMany.
- Attributes mapped with @Enumerated.
- Attributes mapped with @Temporal.

Therefore, do not use a converter to turn an entity association into a foreign key. Entity relationships must be mapped with relationship annotations and foreign keys managed by the relationship mapping.

For enums, choose one of two approaches:

- Use @Enumerated(EnumType.STRING) if you want to store the enum name.
- Use AttributeConverter if you want to store custom codes or formats.

Do not place @Enumerated and @Convert on the same attribute at the same time. They describe two different conversion strategies and should not be combined.

## 7. Converting Attributes Inside an Embeddable

An entity can contain an @Embeddable object, and that object can have basic attributes needing separate conversion.

For example, an address has a postal code stored in a legacy format:

~~~java
package example.domain;

import jakarta.persistence.Embeddable;

@Embeddable
public class Address {

    private String street;
    private String postalCode;

    protected Address() {
    }

    public Address(String street, String postalCode) {
        this.street = street;
        this.postalCode = postalCode;
    }

    public String getStreet() {
        return street;
    }

    public String getPostalCode() {
        return postalCode;
    }
}
~~~

Suppose Java uses a PostalCode value type while the database stores String. A converter can be placed on the embedded attribute using attributeName:

~~~java
@Embedded
@Convert(
    attributeName = "postalCode",
    converter = PostalCodeConverter.class
)
private Address address;
~~~

**attributeName** specifies the attribute inside the embeddable to convert. With nested embeddables, dot-separated attribute paths such as address.postalCode can be used at the appropriate mapping scope.

If an embeddable has multiple attributes requiring different converters, @Converts can be used to declare multiple @Convert annotations:

~~~java
@Embedded
@Converts({
    @Convert(
        attributeName = "postalCode",
        converter = PostalCodeConverter.class
    ),
    @Convert(
        attributeName = "countryCode",
        converter = CountryCodeConverter.class
    )
})
private Address address;
~~~

The attributeName must match the Java attribute name according to the mapping's access strategy, not the SQL column name. When using property access, specify the mapped property name.

Do not use AttributeConverter to turn an entire multi-column embeddable into a single value if the goal is to store each component in separate columns. Use @Embeddable and convert individual basic attributes.

## 8. Converting Elements of an ElementCollection

@ElementCollection maps a collection of basic values or embeddable values. A converter can apply to basic elements of the collection.

For example, the system stores a set of label codes:

~~~java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    private Long id;

    @ElementCollection
    @CollectionTable(
        name = "customer_tags",
        joinColumns = @JoinColumn(name = "customer_id")
    )
    @Column(name = "tag_code")
    @Convert(converter = TagCodeConverter.class)
    private Set<TagCode> tags = new HashSet<>();
}
~~~

Here the converter converts each TagCode into its corresponding database value. It does not convert the entire Set into a single string. The customer_tags table has one row per collection element and a foreign key to customer.

If the collection contains embeddables, apply the converter to basic attributes inside the embeddable using attributeName per mapping rules.

For Maps, values and keys may require separate rules. Jakarta Persistence provides @MapKeyConvert to convert the map key type. Do not confuse a map key converter with a converter applied to map values or collection elements.

## 9. Converters and JPQL / Spring Data Repositories

JPQL works with entity names and Java attributes. With the converted status attribute, queries can still be expressed in terms of the Java type:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatus(OrderStatus status);
}
~~~

Or declared with JPQL:

~~~java
@Query("""
    select p
    from PurchaseOrder p
    where p.status = :status
    """)
List<PurchaseOrder> findByStatus(@Param("status") OrderStatus status);
~~~

Here the parameter is OrderStatus.PAID, not the string "P". The provider uses the attribute's mapping to convert the value to the database representation when generating SQL.

When writing native SQL, you work directly with column names and database representations. For example, the SQL condition compares status_code with 'P'. If returning scalars or DTOs from a native query, do not assume the entity's converter will automatically apply to every custom result; specify result types explicitly and test with the provider in use.

For bulk JPQL update/delete queries, these operations act directly on the database and do not synchronize individual managed entities like ordinary object mutations. When using bulk queries with converted attributes, verify parameter types, mappings, and the persistence context after execution.

## 10. Good Converter Design Rules

A reliable converter should follow these principles:

1. **Bidirectional consistency**: a valid value converted Java → database → Java must preserve its meaning.
2. **Intentional null handling**: do not invoke methods on null and do not silently turn null into another business value without an explicit rule.
3. **Fail on invalid data**: do not silently convert unknown codes into a default value.
4. **Stateless**: do not store per-request or per-entity state in converter fields.
5. **No hidden environment dependencies**: avoid reading files, calling network APIs, or querying the database inside a converter.
6. **Do not put complex business logic in converters**: converters only transform representations, they do not execute business workflows.
7. **Clear database type**: choose Y as a basic type supported by the provider and JDBC.
8. **Backward compatibility with existing data**: changing stored codes requires a migration or compatibility plan.
9. **Test both directions**: verify stored codes, read-back values, nulls, and invalid data.

Converters are typically managed by the provider and may be reused across many persistence operations. Therefore, do not assume each entity gets its own converter instance or that a converter is called only once. Write converters as stateless components safe for repeated invocation.

## 11. Limitations of AttributeConverter

AttributeConverter is suitable when one Java attribute maps to one database value. It is not a general tool for altering persistence structure.

Important limitations:

- **Cannot split one object into multiple columns**: Y is a single database type for a single attribute value. If multiple columns are needed, use @Embeddable or an appropriate mapping.
- **Does not replace entity relationships**: relationships must be declared with @ManyToOne, @OneToMany, or corresponding annotations.
- **Does not replace schema migrations**: converters transform values at the Java/database boundary; they do not automatically fix old data or alter column types.
- **Does not replace validation**: converters can reject invalid data, yet input rules should still be validated at appropriate layers and the database still needs constraints.
- **Not a complete security encryption mechanism**: if conversion involves encryption, you must design key management, rotation, searchability, indexing, and data compatibility; never hardcode secrets inside a converter.
- **Should not be used for types already well supported by the provider**: unnecessary conversion can strip metadata or semantics inherent to the Java type.

If you need to map a domain value into a multi-column structure, consider an embeddable. If you need database-specific type mappings, custom queries, or provider-specific behavior, evaluate the provider's extension APIs after understanding their coupling implications.

## 12. Changing Converters and Existing Data

A converter is part of the contract between Java code and database data. If codes change:

| Change | Risk |
|---|---|
| Changing code N to NEW | Old data can no longer be read properly if the converter does not support the old code |
| Removing an enum constant | Records storing the corresponding code may fail when read |
| Changing database type String to Integer | Schema and data require synchronized migration |
| Enabling autoApply | Attributes of the same type in the persistence unit may change how they are stored |
| Changing the converter class | Mappings and related queries must be re-verified |

For example, if the PAID code changes from P to S, you must decide how to handle records containing P. You can deploy a converter that temporarily reads both P and S while writing only S, then migrate the data and remove support for the old code in a later release. This process must be tested with real data and a rollback plan.

Do not deploy converter changes without checking the schema, data, JPQL, native SQL, reports, and other applications reading the same table.

## 13. Testing AttributeConverter

### 13.1. Unit tests for both methods

A converter can be tested directly without starting Spring:

~~~java
import example.domain.OrderStatus;
import example.persistence.OrderStatusConverter;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class OrderStatusConverterTest {

    private final OrderStatusConverter converter =
        new OrderStatusConverter();

    @Test
    void convertsEnumToDatabaseCode() {
        assertEquals(
            "P",
            converter.convertToDatabaseColumn(OrderStatus.PAID)
        );
    }

    @Test
    void convertsDatabaseCodeToEnum() {
        assertEquals(
            OrderStatus.PAID,
            converter.convertToEntityAttribute("P")
        );
    }

    @Test
    void preservesNull() {
        assertNull(converter.convertToDatabaseColumn(null));
        assertNull(converter.convertToEntityAttribute(null));
    }

    @Test
    void rejectsUnknownDatabaseCode() {
        assertThrows(
            IllegalArgumentException.class,
            () -> converter.convertToEntityAttribute("Z")
        );
    }
}
~~~

These tests verify pure Java conversion rules. They do not verify that the provider discovers the converter, generates the right schema, or invokes the converter during persistence operations.

### 13.2. Integration tests with the JPA provider

Integration tests should be added to verify the full mapping:

1. Start the persistence unit or Spring context using the real provider.
2. Persist a PurchaseOrder with status PAID.
3. Flush and verify the status_code column value is P.
4. Clear the persistence context so the same managed object is not simply returned again.
5. Reload the entity from the database.
6. Verify the status read back is OrderStatus.PAID.
7. Test repository queries with an OrderStatus.PAID parameter.
8. Test invalid database data and how the application reports errors.

Clearing the persistence context is critical: if you only read the same managed object again, the result may come from memory rather than the database → Java conversion.

Additionally, inspect DDL or migrations to verify column type, length, and constraints match the converter codes.

## 14. Common Errors and How to Fix Them

**1. Converter is not applied**

Check whether the class has @Converter, whether the entity attribute has @Convert, or whether the converter has autoApply = true. Ensure the converter belongs to the persistence unit and its package/class is scanned according to configuration.

**2. Incorrect data written to the database**

Check type Y, convertToDatabaseColumn() logic, column name, length, and mapping. Read the value directly from the database to distinguish converter bugs from query or cache issues.

**3. Unable to read old data**

Check whether convertToEntityAttribute() supports all existing codes. Inspect legacy data, write a migration, or deploy a controlled compatibility phase.

**4. Enum stored as ordinal despite having a converter**

Check if @Enumerated is still present on the field/property. Do not combine @Enumerated with @Convert on the same attribute.

**5. Automatic converter affects unintended fields**

Check @Converter(autoApply = true) and all mapped attributes of the same type in the persistence unit. If the rule only applies locally, switch to autoApply = false and declare @Convert explicitly.

**6. JPQL works but native SQL fails**

JPQL uses Java attributes; native SQL uses database column representations. Check whether parameters and literals in native queries use the right stored codes.

**7. Failure when reading invalid data**

Inspect the stack trace to determine whether the converter throws an error in convertToEntityAttribute(). Do not mask errors with default values if doing so alters business meaning.

**8. Converter attempts to convert multiple columns**

An AttributeConverter is not a multi-column mapping. Use @Embeddable, multiple basic attributes, or a specialized mapping solution.

## 15. Workflow for Implementing a Converter

When adding a converter to a project, follow this sequence:

1. Identify the Java type and current database representation.
2. Determine valid values and null-handling rules.
3. Inspect existing data and the actual schema.
4. Design the two inverse conversion methods.
5. Decide between @Convert and autoApply.
6. Check limitations: id, version, relationships, @Enumerated, and @Temporal.
7. Write unit tests for conversion and invalid data.
8. Write integration tests for persist/read/query with the real provider.
9. Prepare migrations if formats or schemas change.
10. Deploy in a way compatible with existing data.

## 16. Self-Assessment Checklist

- [ ] I can explain AttributeConverter<X, Y> and the meanings of X and Y.
- [ ] I can distinguish convertToDatabaseColumn() from convertToEntityAttribute().
- [ ] I can write a converter for an enum using stable database codes.
- [ ] I know how to attach a converter with @Convert.
- [ ] I understand the scope of @Converter(autoApply = true).
- [ ] I know when to use @Converts and attributeName.
- [ ] I understand converters for element collections and map keys.
- [ ] I know that id, version, relationship, @Enumerated, and @Temporal attributes do not have converters applied.
- [ ] I do not combine @Enumerated and @Convert on the same field.
- [ ] I test null, valid codes, and invalid codes.
- [ ] I understand why integration tests must flush and clear the persistence context.
- [ ] I know converters do not replace migrations, validation, or multi-column mappings.

## 17. Review Questions

**1. What does AttributeConverter<X, Y> mean?**

X is the Java type of the domain attribute; Y is the database type used to store the value. The converter provides two methods converting between the two types.

**2. How does @Convert differ from @Converter?**

@Converter marks a converter implementation class and can declare autoApply. @Convert attaches a converter to a specific attribute or specifies conversion for an attribute inside an embedded mapping.

**3. When should autoApply be enabled?**

When all mapped attributes of the same Java type in the persistence unit need the exact same conversion rule. If rules differ by field, use explicit @Convert.

**4. Should AttributeConverter be used for foreign keys?**

No. Entity relationships and foreign keys are managed by relationship mappings. Converters are for basic attribute values.

**5. Why should a converter not silently replace invalid values with a default?**

Because doing so can hide corrupted data and alter business meaning. Report a clear error or implement a controlled backward-compatibility policy.

**6. Why must the persistence context be cleared in integration tests?**

So the subsequent read actually retrieves data via the provider from the database and exercises the convertToEntityAttribute() direction, instead of simply receiving the object already in memory.

When AttributeConverter is used properly, the domain model can keep expressive Java types while the database continues using stable storage representations suited to the system schema.
