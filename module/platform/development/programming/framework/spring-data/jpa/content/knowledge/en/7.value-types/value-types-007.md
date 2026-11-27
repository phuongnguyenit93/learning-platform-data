# Applying autoApply and Limitations of AttributeConverter

JPA AttributeConverter allows converting a data type in the Java model into a basic type that the database can store, and converting it back when reading data. When declaring **@Converter(autoApply = true)**, the provider automatically applies the converter to matching attributes in the persistence unit. This mechanism reduces repeating **@Convert** across multiple entities, but should only be used when the same Java type always shares the same storage rule.

This lesson focuses on how autoApply works, how to override or disable conversion on individual attributes, which attribute types are unsupported by converters, and key limitations to keep in mind when designing converters.

## 1. What Problem Does AttributeConverter Solve?

Suppose the Java model uses an EmailAddress value object instead of storing emails as Strings everywhere. The database can still store that value in a VARCHAR column. AttributeConverter acts as a bridge between the domain type and the database type:

```text
Entity attribute: EmailAddress
          |
          | convertToDatabaseColumn(...)
          v
Database value: String / VARCHAR
          |
          | convertToEntityAttribute(...)
          v
Entity attribute: EmailAddress
```

JPA defines the generic interface:

```java
public interface AttributeConverter<X, Y> {
    Y convertToDatabaseColumn(X attribute);

    X convertToEntityAttribute(Y dbData);
}
```

Where:

- **X** is the Java type of the entity attribute.
- **Y** is the Java type representing the database data that the provider can map to a basic JDBC/database type.
- convertToDatabaseColumn converts the value from the entity to the stored value.
- convertToEntityAttribute converts the value read from the database into the entity's value.

A converter is not a general-purpose JSON serializer and does not replace entity relationships. It fits a basic value or value object representable by a single basic database type, such as EmailAddress to VARCHAR, Money to DECIMAL when only one currency is involved, or a business code to CHAR/VARCHAR.

## 2. Creating and Manually Applying a Converter

Example creating the EmailAddress value object:

```java
public record EmailAddress(String value) {

    public EmailAddress {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Email address must not be blank"
            );
        }

        value = value.trim();
    }
}
```

The value object enforces data validity at the Java layer. The converter handles its database representation:

```java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class EmailAddressConverter
        implements AttributeConverter<EmailAddress, String> {

    @Override
    public String convertToDatabaseColumn(EmailAddress attribute) {
        return attribute == null ? null : attribute.value();
    }

    @Override
    public EmailAddress convertToEntityAttribute(String dbData) {
        return dbData == null ? null : new EmailAddress(dbData);
    }
}
```

An entity can apply the converter explicitly:

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Convert(converter = EmailAddressConverter.class)
    @Column(name = "email", nullable = false, length = 254)
    private EmailAddress email;

    protected Customer() {
    }
}
```

When writing the entity, the provider calls convertToDatabaseColumn and stores the String into the email column. When reading the entity, the provider fetches the String from the database and calls convertToEntityAttribute to construct EmailAddress.

A converter handles both directions. If it only converts properly on write without being able to restore the right value on read, the mapping will fail the entity's requirements.

### 2.1. Handling nulls

The example above returns null when the input is null. This is the common implementation to preserve database NULL semantics.

Distinguish clearly:

- Java null is normally converted to SQL NULL.
- An empty string "" is not the same as NULL.
- A whitespace-only string may be rejected by the value object.
- If a database column contains invalid legacy data, convertToEntityAttribute may throw an exception on read.

Do not silently turn invalid data into a default value because doing so can mask data corruption. If legacy data exists, define explicit migration or compatibility rules.

## 3. How Does autoApply = true Work?

The Converter annotation has an autoApply attribute. The default is false:

```java
@Converter
public class EmailAddressConverter
        implements AttributeConverter<EmailAddress, String> {
    // ...
}
```

With this default, the converter is only applied when specified by @Convert or an equivalent configuration mechanism. If you want the provider to apply it automatically to attributes of type EmailAddress, declare:

```java
@Converter(autoApply = true)
public class EmailAddressConverter
        implements AttributeConverter<EmailAddress, String> {
    // ...
}
```

When autoApply = true, the converter is applied to persistent attributes matching type X in the persistence unit, except for cases excluded by JPA rules or where conversion is overridden/disabled on the attribute.

Example:

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    private Long id;

    @Column(name = "primary_email", length = 254)
    private EmailAddress primaryEmail;

    @Column(name = "backup_email", length = 254)
    private EmailAddress backupEmail;
}
```

Both primaryEmail and backupEmail have type EmailAddress, so the autoApply converter is applied without writing @Convert on each field.

This is especially useful when the same value object appears in many entities:

```java
@Entity
@Table(name = "suppliers")
public class Supplier {

    @Id
    private Long id;

    @Column(name = "contact_email", length = 254)
    private EmailAddress contactEmail;
}
```

Supplier.contactEmail is also converted automatically because the attribute has type EmailAddress and the converter is auto-applied in the persistence unit.

**The scope is the persistence unit**, not the entire Java application regardless of configuration. If the application has multiple EntityManagerFactories/persistence units, verify that the converter is discovered and applied in each persistence unit per provider configuration. Do not assume an automatic converter is shared across every EMF in the application.

## 4. Which Types Does autoApply Target?

A converter declares source type X in AttributeConverter<X, Y>. autoApply targets attributes whose Java type corresponds to X. For example:

```java
AttributeConverter<EmailAddress, String>
```

means this converter targets EmailAddress attributes, not every String in an entity.

This prevents accidentally transforming all String columns. If a converter is declared for a type that is too broad, such as String, autoApply can affect many attributes that do not share the same business meaning. Create a dedicated value object for data needing conversion rather than applying a global converter to a broad foundational type.

Converters can apply to basic attributes declared in entities, mapped superclasses, embeddables, and basic elements in collections according to JPA mapping rules. A converter handles each matching value individually; it does not convert an arbitrary object graph or collection into a database relationship.

## 5. Overriding autoApply with @Convert

There are cases where most EmailAddress attributes use the default converter, while one field must use a different representation for compatibility with a legacy schema. In that case, a specific converter can be specified on the attribute:

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    private Long id;

    private EmailAddress primaryEmail;

    @Convert(converter = LegacyEmailAddressConverter.class)
    @Column(name = "legacy_email")
    private EmailAddress legacyEmail;
}
```

In this example:

- primaryEmail uses EmailAddressConverter via autoApply.
- legacyEmail uses the explicitly specified LegacyEmailAddressConverter.
- The converter specified on the attribute takes precedence to determine conversion for that specific attribute.

The alternative converter must be declared as a valid JPA converter:

```java
@Converter
public class LegacyEmailAddressConverter
        implements AttributeConverter<EmailAddress, String> {

    @Override
    public String convertToDatabaseColumn(EmailAddress attribute) {
        if (attribute == null) {
            return null;
        }
        return "legacy:" + attribute.value();
    }

    @Override
    public EmailAddress convertToEntityAttribute(String dbData) {
        if (dbData == null) {
            return null;
        }

        String prefix = "legacy:";
        if (!dbData.startsWith(prefix)) {
            throw new IllegalArgumentException(
                "Unexpected legacy email representation"
            );
        }

        return new EmailAddress(dbData.substring(prefix.length()));
    }
}
```

This is an example illustrating a legacy storage format. In real projects, only use a prefix rule if the legacy schema and data truly require it. When changing storage formats, a migration or compatible reading strategy is required so existing data is not broken.

Avoid creating multiple converters with autoApply = true for the same type X in the same persistence unit. If a type has multiple representations, choose one default converter and use @Convert to mark exceptions explicitly. This keeps mappings easy to understand and avoids ambiguous converter configurations.

## 6. Disabling Auto Conversion on an Attribute

JPA can disable an automatic converter for a specific attribute using:

```java
@Convert(disableConversion = true)
private SomeBasicType value;
```

The disableConversion attribute means automatic converters are not applied to that field. Note carefully: after disabling the converter, the attribute type must still have a valid mapping supported by JPA/the provider.

For example, if the attribute is of type String, the provider already knows how to map String to VARCHAR without a converter. However, if the attribute is a custom EmailAddress type and no converter applies anymore, the provider typically does not know how to store that type. Disabling conversion in that case can cause EntityManagerFactory initialization to fail or produce an invalid mapping.

Do not use disableConversion as a way to "suppress a converter error." Verify whether the remaining Java type is a basic type supported by the provider.

If the attribute needs a different storage rule, prefer using @Convert(converter = ...) to select the appropriate converter instead of disabling conversion and hoping the provider understands a custom value object.

## 7. Attribute Types Unsupported by Converters

AttributeConverter is not a tool for converting every kind of mapping. Under JPA rules, converters are not applied to attributes that:

- Have @Id or @EmbeddedId.
- Have @Version.
- Are entity relationships: @OneToOne, @OneToMany, @ManyToOne, or @ManyToMany.
- Have @Enumerated.
- Have @Temporal.

These categories have their own JPA mapping rules. Do not attempt to use AttributeConverter to replace relationship mappings, identifier keys, optimistic locking, enum mappings, or temporal mappings specified by those annotations.

### 7.1. Do not use converters for IDs

Do not design a converter to turn a custom primary key type into a different database type when the attribute is marked with @Id. For composite keys, use @EmbeddedId or @IdClass with an appropriate mapping.

If you want a value object to represent an ID in the domain, evaluate key mapping mechanisms supported by JPA/the provider and keep entity identity explicit. Do not rely on autoApply to convert IDs.

### 7.2. Do not use converters for version

@Version is used by the provider for optimistic locking control. Do not use AttributeConverter to transform a version field. Let the provider manage supported version types such as numeric or timestamp per the JPA specification.

### 7.3. Do not use converters for entity relationships

A ManyToOne relationship cannot be converted into an arbitrary code string using AttributeConverter. Relationships must be mapped using associations and foreign keys:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id")
private Customer customer;
```

If the database only stores customer_code and does not need association management, it can be modeled as a basic attribute like String or a CustomerCode value object. Once modeled as an entity relationship, use JPA relationship mappings instead of a converter.

### 7.4. Do not combine converters with @Enumerated or @Temporal

An enum can be stored by name or ordinal via @Enumerated. If custom storage such as codes "P", "C", "X" is required, use an AttributeConverter for the enum and do not annotate the attribute with @Enumerated.

Example:

```java
public enum OrderStatus {
    PENDING, CONFIRMED, CANCELLED
}

@Converter(autoApply = true)
public class OrderStatusConverter
        implements AttributeConverter<OrderStatus, String> {

    @Override
    public String convertToDatabaseColumn(OrderStatus status) {
        if (status == null) {
            return null;
        }

        return switch (status) {
            case PENDING -> "P";
            case CONFIRMED -> "C";
            case CANCELLED -> "X";
        };
    }

    @Override
    public OrderStatus convertToEntityAttribute(String code) {
        if (code == null) {
            return null;
        }

        return switch (code) {
            case "P" -> OrderStatus.PENDING;
            case "C" -> OrderStatus.CONFIRMED;
            case "X" -> OrderStatus.CANCELLED;
            default -> throw new IllegalArgumentException(
                "Unknown order status code: " + code
            );
        };
    }
}
```

Do not place @Enumerated(EnumType.STRING) on the same OrderStatus field if you want the converter to control the representation. For date/time types, JPA already supports many java.time types; use standard mappings unless special storage rules exist. @Temporal is primarily for legacy Date/Calendar types and must not be combined with converters per JPA rules.

## 8. Converters Must Map to a Basic Database Type

Type Y in AttributeConverter<X, Y> must be a type that the provider can map to a basic database type. Common types include String, Integer, Long, BigDecimal, Boolean, LocalDate, or other basic types supported by the provider.

Sensible examples:

- EmailAddress → String.
- CountryCode → String.
- Money → BigDecimal when currency is fixed or stored elsewhere.
- ExternalReference → UUID or String depending on schema.

Avoid using a converter to serialize an object with multiple relationships into a JSON string merely to avoid table design. That approach loses relational querying, constraints, joins, and per-component updates. If JSON storage is genuinely needed, consider native/provider-specific JSON types, embeddables, collection mappings, or an appropriate database schema design.

A converter should generally be stateless and thread-safe. Do not keep entity state in mutable fields, do not hold request context, and do not run database queries or HTTP calls from inside a converter. Conversion happens during ORM reads/writes; side effects can cause recursion, poor performance, and hard-to-test behavior.

## 9. Converters and Spring Data JPA Queries

With derived queries or JPQL on an attribute mapped by a converter, the application passes values in Java type X. The provider handles converting the parameter to type Y when generating SQL.

Example:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByPrimaryEmail(EmailAddress email);
}
```

The method accepts EmailAddress because that is the attribute's type on the entity. Do not change the method parameter to String just because the database stores VARCHAR.

With JPQL:

```java
@Query("""
    select c
    from Customer c
    where c.primaryEmail = :email
    """)
Optional<Customer> findByEmail(
    @Param("email") EmailAddress email
);
```

JPQL references Java entities and properties. The provider uses the converter mapping to handle the corresponding values.

With native SQL, the query operates directly on physical tables/columns and database types. Whether converters apply to native query parameters/results can depend on how the provider resolves mappings. Do not assume every native query automatically converts every custom type. When native queries are needed, test with the exact provider/database; you can pass type Y or use projections/mappings suited to the API in use.

Converters also do not automatically handle HTTP JSON serialization. Jackson serialization/deserialization of requests/responses is a separate mechanism. If an API receives an email as a string, map the DTO to EmailAddress at the application boundary; AttributeConverter serves persistence only.

## 10. Schema, Column Definitions, and Validation

Converters do not replace column design. If X converts to Y as a String, the database column needs an appropriate length and data type:

```java
@Convert(converter = EmailAddressConverter.class)
@Column(name = "email", nullable = false, length = 254)
private EmailAddress email;
```

If Y is BigDecimal, consider precision and scale:

```java
@Column(name = "amount", precision = 19, scale = 2)
private Money amount;
```

In the Money example, the converter must return BigDecimal and the representation must preserve business meaning. If Money carries a currency code, converting only the amount to BigDecimal drops the currency. When multiple currencies are supported, store currency separately or design a more appropriate mapping, such as an embeddable containing amount and currency.

With migration-managed schemas, migrations must create columns with the right type, length, precision, nullability, indexes, and constraints. @Column describes the mapping; @Convert describes the value conversion; the two annotations address two distinct concerns.

## 11. Common Mistakes

| Symptom | Common cause | Resolution |
|---|---|---|
| Converter is not auto-applied | Missing autoApply = true or converter not discovered in the persistence unit | Check @Converter and EMF configuration |
| Converter applied unintentionally | autoApply placed on an overly broad Java type | Use a dedicated value object or choose explicit @Convert |
| Error when reading data | Old DB value does not match format expected by converter | Inspect legacy data, migrate, and handle errors explicitly |
| EntityManagerFactory fails to start | Custom type lacks a valid mapping after disabling conversion | Choose a converter or a provider-supported basic type |
| Enum does not use custom code | Combining @Enumerated with AttributeConverter | Remove @Enumerated when using a converter for an enum |
| Converter does not run on ID/version | JPA excludes these attributes | Design ID/version mappings using standard JPA mechanisms |
| JPQL reports entity not found | Using table name instead of entity name | Use entity names and Java properties in JPQL |
| Native query has wrong column name | Using Java property instead of database column | Use physical table/column names in SQL |
| Stored column truncates data | Y is longer than column length or old schema | Set appropriate length and migrate schema |
| Incorrect value comparisons | Conversion alters normalization or representation | Test round-trip behavior and value object equals/hashCode rules |

## 12. Practice Exercises

1. Create an EmailAddress value object and a converter to String.
2. Mark the converter with @Converter(autoApply = true), then use EmailAddress in two different entities.
3. Verify the data stored in the database is VARCHAR and reading it back yields EmailAddress.
4. Create an alternative converter for a legacy field and apply it with @Convert(converter = ...).
5. Try disableConversion on an attribute with a provider-supported basic type; observe the difference.
6. Try combining @Enumerated with a converter in a separate mapping and read the error message/verify provider rules.
7. Write a derived query accepting EmailAddress and confirm the parameter is converted.
8. Write JPQL using the EmailAddress property; compare it with a native query using the email column.
9. Try reading an invalid legacy value and decide on a data migration strategy.
10. Write a round-trip test: Java value → database value → Java value; verify equality and null behavior.

**Overarching principle:** autoApply enables consistent use of a converter for attributes with matching Java types within a persistence unit. Use @Convert to pick a specific converter or disable conversion when the remaining type still has a valid mapping. AttributeConverter is strictly for basic values under JPA rules; do not use it to replace ID, version, relationship, enum/temporal mappings, or entire object graphs.
