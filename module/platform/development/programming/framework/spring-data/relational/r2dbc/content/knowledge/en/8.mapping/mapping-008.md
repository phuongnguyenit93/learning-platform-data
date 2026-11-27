# Mapping Nested Objects and Version-Specific Limitations

In a Java model, an entity often contains child objects to represent business values. For example, `Customer` might contain `Address`, `Order` might contain a list of `OrderLine` items, or a profile might contain a `Preferences` object. However, nesting one object inside another in Java does not by itself dictate how its data is stored in a relational database.

With Spring Data R2DBC, you must explicitly choose a mapping strategy for each kind of nested data. A value object can be embedded into the same row using `@Embedded`; an aggregate-owned collection can be stored in a separate table using `@MappedCollection`; another aggregate is usually referenced by identifier; and data that must be stored as a JSON structure may require driver-dependent custom converters. These approaches have distinct semantics and cannot be substituted for one another arbitrarily.

## 1. Choosing a Storage Strategy for Nested Objects

Before writing annotations, determine which case applies to the child object:

| Java Model | Typically Suitable Mapping | Relational Data Structure |
|---|---|---|
| Value object owned by the entity, without independent identity | `@Embedded` | Fields of the child object become columns in the same row as the parent entity. |
| Elements belonging to the aggregate root, potentially multiple elements | `@MappedCollection` | Elements are stored in a separate table and linked back to the aggregate root via an identifier column. |
| Reference to an independent aggregate | Store the ID or use `AggregateReference` | The current aggregate's table holds a reference key; the other aggregate is loaded by a separate query when needed. |
| Value that must be stored as a JSON structure | Custom conversion and driver-supported JSON data type | A JSON/JSONB column or equivalent database type. |
| Aggregated read data from multiple tables | SQL join and projection/DTO | The query returns the required columns; the application maps them into a read model. |

For instance, a shipping address is typically a value object of an order. It does not need an independent lifecycle and can be stored directly in the `purchase_order` row. Conversely, an order references a customer, which is another aggregate; nesting the entire `Customer` object inside `PurchaseOrder` blurs aggregate boundaries and complicates update control.

## 2. Embedding Value Objects in the Same Table with @Embedded

`@Embedded` tells Spring Data Relational that a property is an object mapped onto the same row as its containing entity. The child object's properties become separate columns in the parent table. This fits value objects such as addresses, date ranges, monetary info, or a cohesive group of business values.

For example, an order containing a shipping address:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.Table;

import static org.springframework.data.relational.core.mapping.Embedded.OnEmpty.USE_NULL;

@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    @Embedded(prefix = "shipping_", onEmpty = USE_NULL)
    private Address shippingAddress;
}

public class Address {
    private String street;
    private String city;
    private String postalCode;
}
```

With the `shipping_` prefix, the properties of `Address` are mapped to corresponding columns in the `purchase_order` table, such as:

| Java Property | Column in Table `purchase_order` |
|---|---|
| `id` | `id` |
| `orderNumber` | `order_number` (by default naming rules) |
| `shippingAddress.street` | `shipping_street` |
| `shippingAddress.city` | `shipping_city` |
| `shippingAddress.postalCode` | `shipping_postal_code` |

Actual column names also depend on the naming strategy and any declared `@Column` annotations. Prefixes prevent name collisions when the parent entity and multiple embedded objects share property names. You can choose distinct prefixes per property, such as `billing_` and `shipping_` for two addresses of the same `Address` type.

### 2.1 Meaning of prefix and @Column

`prefix` is prepended to the column names of the embedded object. It neither creates a new table nor establishes a foreign-key relationship. The fields still reside in the same data row as the parent entity.

If a specific column name is needed, you can place `@Column` on a property of the value object:

```java
public class Address {
    @Column("street_name")
    private String street;

    private String city;
}
```

When combined with a prefix, verify the final column name according to the mapping rules of the version in use and check it against the schema. Do not assume database column names always match Java field names verbatim.

### 2.2 Handling Empty or Null Embedded Objects

When reading a row, Spring Data must decide how to construct the `Address` property if all columns of the embedded object are `NULL`. The `onEmpty` attribute controls this behavior in the current `@Embedded` API:

- `USE_NULL`: if all columns of the embedded object are empty/null, map the property to `null`.
- `USE_EMPTY`: instantiate the embedded object even if all of its columns are empty/null.

Example:

```java
@Embedded(prefix = "billing_", onEmpty = USE_NULL)
private Address billingAddress;

@Embedded(prefix = "contact_", onEmpty = Embedded.OnEmpty.USE_EMPTY)
private ContactDetails contactDetails;
```

Choose `USE_NULL` when the object only has meaning if at least one field is stored. Choose `USE_EMPTY` when the domain model requires the property to always hold an object, even when component fields have no values yet. Ensure the object type can be instantiated by Spring Data under the configured constructor/property access strategy.

All columns of an embedded object may be `NULL` when data has not been entered yet or when the application actively saves an empty object. Therefore, choosing `onEmpty` is a data-modeling decision, not merely a Java object presentation preference.

## 3. Nested Objects Inside an Aggregate: @MappedCollection

Not every child object fits `@Embedded`. When an aggregate root contains a collection of multiple elements, those elements usually need to be stored in a separate table. `@MappedCollection` describes an aggregate-owned collection and the column linking child rows back to the aggregate root.

For example, an order with multiple order lines:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;
import java.util.List;

@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines;
}

@Table("order_line")
public class OrderLine {
    private String productCode;
    private int quantity;
}
```

With this mapping, `purchase_order` stores the aggregate root, while the elements are stored in `order_line`. The `order_id` column in the child table links each line to the corresponding order. When Spring Data saves the aggregate root, collection elements are handled according to aggregate mapping.

If the collection is ordered, a column storing the index may be required to restore element order. `@MappedCollection` supports declaring `keyColumn` when a collection key/index column needs to be stored:

```java
@MappedCollection(idColumn = "order_id", keyColumn = "line_position")
private List<OrderLine> lines;
```

The schema must have the corresponding columns. With a `Map`, the key column can store each entry's key. Table names, ID columns, and key columns must align with the project's migrations.

`@MappedCollection` expresses relationships inside an aggregate. It does not turn arbitrary associations between entities into automatically managed relationships as in a full ORM. Keep collections scoped to the aggregate root and avoid using them to load an unbounded object graph.

## 4. Referencing Another Aggregate by Identifier

When an entity needs to reference an independent aggregate, a common design is to store the ID of the other aggregate. For example, `PurchaseOrder` stores `customerId` instead of embedding the entire `Customer` into the object graph.

```java
@Table("purchase_order")
public class PurchaseOrder {
    @Id
    private Long id;

    private Long customerId;
}
```

Spring Data Relational also provides `AggregateReference` to make a reference to another aggregate explicit:

```java
import org.springframework.data.relational.core.mapping.AggregateReference;

@Table("purchase_order")
public class PurchaseOrder {
    @Id
    private Long id;

    private AggregateReference<Customer, Long> customer;
}
```

`AggregateReference<Customer, Long>` represents the identifier of a `Customer` aggregate whose ID type is `Long`. It lets the domain model express that the property references another aggregate. It does not automatically load `Customer`, create a lazy proxy, or synchronize the customer object when the order is saved.

When customer name or detailed data is needed, the application runs a separate query or writes an SQL join for the read use case. This keeps update boundaries between aggregates clear and avoids relying on the framework traversing an object graph automatically.

## 5. Storing Nested Objects as JSON

Sometimes a child object is a flexible structure, rarely queried by individual attributes, or has a frequently changing schema. When the database supports JSON/JSONB, the application may choose to store the object in a JSON column.

Do not assume that any POJO declared as a property will automatically serialize to JSON. Suitable conversion is required between the Java type and the data type provided by the R2DBC driver. Exact source/target types depend on the database and driver; for example, PostgreSQL R2DBC provides its own `Json` type in the driver.

Illustrative converter example for PostgreSQL:

```java
import io.r2dbc.postgresql.codec.Json;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class PreferencesWriteConverter
        implements Converter<Preferences, Json> {

    private final ObjectMapper objectMapper;

    public PreferencesWriteConverter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public Json convert(Preferences source) {
        try {
            return Json.of(objectMapper.writeValueAsString(source));
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException("Cannot serialize preferences", ex);
        }
    }
}

@ReadingConverter
public class PreferencesReadConverter
        implements Converter<Json, Preferences> {

    private final ObjectMapper objectMapper;

    public PreferencesReadConverter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public Preferences convert(Json source) {
        try {
            return objectMapper.readValue(source.asString(), Preferences.class);
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException("Cannot deserialize preferences", ex);
        }
    }
}
```

This example uses the PostgreSQL driver's JSON type; imports, constructors, and converters must be adapted to your application's dependency versions. Register reading/writing converters in Spring Data R2DBC custom conversions so the mapping context uses them. The schema must also declare the column with an appropriate JSON/JSONB type.

JSON lets you store flexible structures in a single column, with trade-offs:

- Inner fields are no longer independent relational columns under normal mapping.
- Querying, indexing, and partially updating JSON depend on the database management system's capabilities.
- Data constraints and type checks may be looser than with normalized relational columns.
- Converters must handle serialization errors, JSON schema evolution, and compatibility with data stored by older application versions.

Choose JSON when the data structure suits this storage format, not merely to avoid declaring relational columns.

## 6. Querying Multiple Tables and Mapping into Nested DTOs

Another scenario is displaying aggregated data from multiple tables. This is typically a read need, not necessarily an aggregate to be persisted as an object graph. You can write an SQL join and return a projection or DTO containing exactly the required data.

For example, an order list screen needs the order number, customer name, and shipping city:

```java
public record OrderListRow(
    Long orderId,
    String orderNumber,
    String customerName,
    String shippingCity
) {}

@Query("""
    SELECT o.id AS orderId,
           o.order_number AS orderNumber,
           c.name AS customerName,
           o.shipping_city AS shippingCity
    FROM purchase_order o
    JOIN customer c ON c.id = o.customer_id
    ORDER BY o.id
    """)
Flux<OrderListRow> findOrderList();
```

Flat DTOs are usually simple and clear for aggregated queries. If an API requires nested objects like `OrderView` containing `CustomerView` and `AddressView`, you can map from the flat projection to the response object at the application layer, or use custom row mapping when detailed control over the result is needed.

Do not assume an SQL join will automatically hydrate an entire relationship into an object graph like JPA lazy/eager fetching. The SQL query determines which columns are returned, while building nested DTOs should be explicit in mapping or transformation code.

## 7. Limitations of Nested Object Mapping

Spring Data R2DBC provides object mapping, yet its scope is bound to the Spring Data Relational model. Keep these limitations in mind:

### 7.1 Embedded Is Not a Separate-Table Relationship

`@Embedded` merely flattens a value object's properties into the same data row. It does not create a child table, foreign key, or an entity with its own identity. If an object has an independent lifecycle, is referenced by multiple aggregates, or needs independent querying/updating, consider a separate table model and ID reference.

### 7.2 No Automatic Lazy Loading for Nested Objects

Spring Data R2DBC does not use proxies to load child objects when a getter is called. `@Embedded` is read from columns of the same row; `@MappedCollection` is loaded as part of reading the aggregate; an aggregate reference holds only the identifier. When other data is needed, the application issues the corresponding reactive query.

### 7.3 No Automatic Synchronization of Every Object in an Object Graph

There is no JPA-style persistence context tracking changes across all child objects. The application must invoke the appropriate save operation on the aggregate root or corresponding repository. Design transactions if multiple save operations must succeed or fail together.

### 7.4 No Automatic JSON Inference for Arbitrary Types

Complex Java types require conversions understood by both the driver and Spring Data. If the database uses a specialized JSON type, a compatible converter or codec is required. Simply adding a POJO-typed property to an entity does not guarantee the framework will serialize it in the desired format.

### 7.5 Not Every Projection Builds Arbitrary Object Graphs

When executing a join query, SQL output consists of columns and rows. If the return structure has multiple object levels, specify aliases, DTOs, converters, or row mappers explicitly. Do not rely on the framework inferring nested relationships from column names in all cases.

## 8. API Differences Across Spring Data Relational Versions

Mapping examples must match the version of Spring Data Relational used by your application. The embedded-object API has changed across major generations, so an example copied from older documentation may not compile in a newer project.

A notable difference is how null/empty handling is declared for `@Embedded`:

| Version Line | Common Declaration Style |
|---|---|
| Spring Data Relational 2.x | Nested annotations such as `@Embedded.Nullable` and `@Embedded.Empty`, along with `prefix`, may appear. |
| Spring Data Relational 3.x and later | Uses `@Embedded(prefix = "...", onEmpty = USE_NULL)` or `onEmpty = USE_EMPTY`. |

An example using the older API might look like:

```java
@Embedded.Nullable(prefix = "address_")
private Address address;
```

In the newer API, the equivalent expression centers on the `onEmpty` attribute:

```java
@Embedded(prefix = "address_", onEmpty = USE_NULL)
private Address address;
```

Do not mix syntax from two API generations in the same project. When upgrading Spring Data Relational, update imports, annotations, and embedded-object configuration according to the target version's documentation.

Beyond `@Embedded`, check the versions of related components such as `@MappedCollection`, custom conversions, the R2DBC driver, and JSON types. Mapping capability for a data type also depends on the driver: the same database column can be represented by different Java types across drivers.

Spring Boot typically manages Spring Data versions through dependency management/BOM. When using Spring Boot, let versions be managed cohesively rather than upgrading a single Spring Data module to a different major version from the others. When not using Spring Boot, check the compatibility matrix across Spring Framework, Spring Data Relational, Spring Data R2DBC, and the driver.

If an online example fails to compile, check in this order: actual Spring Data Relational version, annotation imports, API signatures in the corresponding Javadoc, and then the data types returned by the driver. Do not fix code by swapping annotations randomly without identifying the API version.

## 9. Design Example Combining Multiple Strategies

An order model can combine a value object, an aggregate-owned collection, and a reference to another aggregate:

```java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    private AggregateReference<Customer, Long> customer;

    @Embedded(prefix = "shipping_", onEmpty = USE_NULL)
    private Address shippingAddress;

    @MappedCollection(idColumn = "order_id", keyColumn = "line_position")
    private List<OrderLine> lines;
}

public class Address {
    private String street;
    private String city;
    private String postalCode;
}

@Table("order_line")
public class OrderLine {
    private String productCode;
    private int quantity;
}
```

In this model:

- `shippingAddress` is a value object stored as `shipping_*` columns directly in `purchase_order`.
- `lines` is a collection of elements belonging to the `PurchaseOrder` aggregate, stored in `order_line` and linked via `order_id`.
- `customer` is a reference to the `Customer` aggregate, represented by its identifier without automatically loading the full customer.

The corresponding schema must be created by migrations and match the table/column names in mapping. The example only illustrates domain structure and annotations; constructors, getters/setters, imports, and instantiation are added per the project's coding style.

## 10. How to Choose and Verify Mapping in a Project

When designing a nested object property, answer these questions in order:

1. Does the object have an independent identity and lifecycle? If yes, consider a separate entity/aggregate and reference it by ID.
2. Is the object an inseparable value part of the parent entity? If yes, `@Embedded` is usually suitable.
3. Is the object an element in a collection owned by the aggregate root? If yes, consider `@MappedCollection` and a child table.
4. Must the data be stored as JSON for flexibility or database requirements? If yes, declare custom converters/codecs matching the driver.
5. Does the nested object only serve a read screen? If yes, an SQL join with a projection/DTO may be cleaner than expanding the aggregate.
6. Which annotation syntax does your project's Spring Data Relational version support? Check the BOM and Javadoc before adopting examples.

After selecting a mapping, align the entity with schema migrations, verify column names after applying prefixes, test the case where all embedded columns are `NULL`, and run read/write queries on the exact driver in use. For JSON, test both serialization/deserialization directions and legacy data. For collections, check foreign link columns and element ordering if order carries business meaning.

Nested object mapping in Spring Data R2DBC works best when the Java structure reflects the actual storage model: value objects are embedded in the same row, aggregate collections reside in child tables, independent aggregates are referenced by ID, and aggregated data is read through queries and projections. Choosing the right strategy and using syntax matching your Spring Data Relational version avoids false expectations about ORM capabilities and keeps mapping stable as the application grows.
