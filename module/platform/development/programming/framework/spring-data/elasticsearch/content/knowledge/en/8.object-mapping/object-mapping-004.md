# Per-Property Conversion with @ValueConverter

In a Java application, an entity property sometimes uses a custom domain data type instead of a primitive type. For instance, a phone number can be represented by a PhoneNumber class, a currency code by CurrencyCode, or an order status by an OrderStatus type. When saving an entity to Elasticsearch, the application may want to represent these types as strings, numbers, or data structures that Elasticsearch understands.

Spring Data Elasticsearch provides the @ValueConverter annotation to attach a converter to a specific property. The converter transforms the Java value into a value storable in Elasticsearch when writing, and transforms it back when reading. The key point is that the converter only applies to the annotated property, even when other properties share the same Java type.

For example, the same PhoneNumber type can be stored in E.164 format in one field, while another property of the same type keeps a different representation. This is where @ValueConverter is more useful than a global type-based converter.

## 1. What Problem Does @ValueConverter Solve?

MappingElasticsearchConverter is the Spring Data Elasticsearch component used to convert Java entities to documents and restore entities from documents. It reads mapping metadata, including annotations such as @Document, @Id, @Field, and custom conversions.

When a Java type needs a custom representation on a property, there are two common options:

- Register a Converter in ElasticsearchCustomConversions. This rule applies by source and target type pair within the mapping context, so every matching property can be affected by the same rule.
- Attach @ValueConverter to the property. This rule applies only to that property and does not automatically affect all properties of the same Java type.

For example, an entity has two fields of the same PhoneNumber type:

~~~java
public class CustomerDocument {

    private PhoneNumber primaryPhone;
    private PhoneNumber importedPhone;
}
~~~

The application may want to store primaryPhone in E.164 format, while importedPhone needs to preserve a different representation rule for compatibility with data imported from a legacy system. Attaching a converter per property clearly expresses this distinction.

According to Spring Data Elasticsearch documentation, @ValueConverter defines the converter class for the annotated property. Unlike a globally registered converter, it converts only that property, not every property with the same data type.

## 2. Where Does the Converter Sit in the Mapping Process?

When writing an entity, the property converter participates in the step where Spring Data builds the document:

~~~text
Java Entity
    |
    v
Spring Data mapping metadata
    |
    v
Read property with @ValueConverter
    |
    v
PropertyValueConverter.write(...)
    |
    v
Elasticsearch native value
    |
    v
JSON document and Elasticsearch client
~~~

When reading a document, the converter runs in the reverse direction:

~~~text
Document from Elasticsearch
    |
    v
Stored value of the property
    |
    v
PropertyValueConverter.read(...)
    |
    v
Java value of the property
    |
    v
Java Entity
~~~

The two methods have distinct roles:

| Method | Conversion Direction | Example |
| --- | --- | --- |
| write(Object value) | Java value to Elasticsearch value | PhoneNumber to string +84901234567 |
| read(Object value) | Elasticsearch value to Java value | String +84901234567 to PhoneNumber |

A converter must be able to read back the format it wrote. If only the write direction is implemented properly without handling the read direction, reading the entity can fail or produce an incorrect value.

## 3. Declaring a PropertyValueConverter

@ValueConverter takes a class implementing the PropertyValueConverter interface in package:

~~~java
org.springframework.data.elasticsearch.core.mapping.PropertyValueConverter
~~~

In the current Spring Data Elasticsearch API, the interface provides two methods, read and write, each accepting and returning an Object.

The example below uses PhoneNumber as a domain type:

~~~java
public final class PhoneNumber {

    private final String e164;

    private PhoneNumber(String e164) {
        if (e164 == null || !e164.startsWith("+")) {
            throw new IllegalArgumentException(
                "Phone number must use an international format"
            );
        }
        this.e164 = e164;
    }

    public static PhoneNumber of(String e164) {
        return new PhoneNumber(e164);
    }

    public String toE164() {
        return e164;
    }
}
~~~

Converter:

~~~java
import org.springframework.data.elasticsearch.core.mapping.PropertyValueConverter;

public final class PhoneNumberValueConverter
        implements PropertyValueConverter {

    @Override
    public Object write(Object value) {
        if (!(value instanceof PhoneNumber)) {
            throw new IllegalArgumentException(
                "Expected a PhoneNumber value"
            );
        }

        PhoneNumber phoneNumber = (PhoneNumber) value;
        return phoneNumber.toE164();
    }

    @Override
    public Object read(Object value) {
        if (!(value instanceof String)) {
            throw new IllegalArgumentException(
                "Expected a stored phone number string"
            );
        }

        return PhoneNumber.of((String) value);
    }
}
~~~

On the write side, the converter extracts the PhoneNumber value and returns an E.164 string. On the read side, the converter receives the string from the document and reconstructs the PhoneNumber.

A converter should focus purely on value conversion. It should not make network queries, read files, call repositories, or contain business logic that depends on the current request. A simple, deterministic, stateless converter without mutable state is much easier to use and test.

### 3.1. Constructor and instantiation rules

Per the @ValueConverter API, if the converter is a regular class, it must have a no-argument constructor so the framework can instantiate it. If using an enum as a singleton converter, the enum must have exactly one constant.

Enum-based converter example:

~~~java
public enum PhoneNumberValueConverter
        implements PropertyValueConverter {

    INSTANCE;

    @Override
    public Object write(Object value) {
        return ((PhoneNumber) value).toE164();
    }

    @Override
    public Object read(Object value) {
        return PhoneNumber.of((String) value);
    }
}
~~~

For a regular class, provide a no-argument constructor:

~~~java
public class PhoneNumberValueConverter
        implements PropertyValueConverter {

    public PhoneNumberValueConverter() {
    }

    // read and write
}
~~~

Do not assume that a converter declared in the annotation will automatically be Spring-injected like a @Component bean. The default factory mechanism may instantiate the converter using its no-argument constructor. If the converter needs dependencies from Spring, configure a PropertyValueConverterFactory or registry suitable for your Spring Data version; the API docs cover factories with BeanFactory support.

## 4. Attaching a Converter to a Property with @ValueConverter

Once you have a converter, place the annotation on the exact field that needs conversion:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.ValueConverter;

@Document(indexName = "contacts")
public class ContactDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    @ValueConverter(PhoneNumberValueConverter.class)
    private PhoneNumber phoneNumber;

    // Constructors, getters and setters
}
~~~

Here there are two separate configurations:

- @ValueConverter converts the Java value of the property to an E.164 string and back.
- @Field(type = FieldType.Keyword) declares the Elasticsearch mapping type for a field stored as a string requiring exact matching.

The converter does not replace the mapping. It determines how the value is represented; @Field or JSON mapping determines how Elasticsearch indexes that value.

For a document with phone number +84901234567, the _source section may look like:

~~~json
{
  "id": "contact-1001",
  "phoneNumber": "+84901234567"
}
~~~

In Java, the property still has type PhoneNumber. The application does not need to change the domain type to String just because Elasticsearch stores the field as a string.

## 5. One Java Type, Multiple Conversions Across Different Properties

This is the most important benefit of @ValueConverter: conversion scope is per-property.

For example, both properties use the PhoneNumber type, yet they can be stored differently:

~~~java
@Document(indexName = "contacts")
public class ContactDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    @ValueConverter(E164PhoneNumberConverter.class)
    private PhoneNumber primaryPhone;

    @Field(type = FieldType.Keyword)
    @ValueConverter(DigitsOnlyPhoneNumberConverter.class)
    private PhoneNumber legacyPhone;
}
~~~

E164PhoneNumberConverter can store strings like +84901234567; DigitsOnlyPhoneNumberConverter can store digit strings like 84901234567. Both converters still restore to the same Java PhoneNumber type.

This is useful when:

- One property needs normalization before indexing, while another needs to keep an old format.
- Two data sources follow different storage conventions.
- A value object type is reused in many places without all of them needing the same representation.
- A field's format needs to change without affecting other properties of the same Java type.

When using multiple converters, class names should clearly describe the storage rule. Avoid generic names like StringConverter, because later it becomes hard to tell which standard the converter enforces.

## 6. Choosing a Mapping Type Compatible with the Converted Value

@ValueConverter does not declare an Elasticsearch mapping type by itself. The field type must match the value returned by write.

| Value Returned by Converter | Typically Suitable Mapping | Example |
| --- | --- | --- |
| String for exact matching | keyword | Identifiers, normalized phone numbers |
| String requiring full-text search | text | Descriptions, content |
| Long or Integer | long or integer | Quantities, truly numeric codes |
| Double or BigDecimal represented as a compatible numeric type | double, scaled_float, or suitable numeric type | Measurements, scores |
| Boolean | boolean | Status flags |
| Map or structured object | object or nested depending on query needs | A multi-part value object |

For example, if PhoneNumberValueConverter.write() returns a string, the field should be declared as keyword when the application needs exact phone number lookups:

~~~java
@Field(type = FieldType.Keyword)
@ValueConverter(PhoneNumberValueConverter.class)
private PhoneNumber phoneNumber;
~~~

If the converter returns a string while the field is mapped as a numeric or other type, Elasticsearch may reject the document or handle the data unexpectedly. Conversely, choosing text for a code requiring exact matching can alter query behavior due to analyzer tokenization.

For converters returning a Map structure, explicitly define the object mapping and sub-fields. If only a scalar value is needed, do not return an unnecessarily complex structure.

## 7. Converting a Value Object to a String

Another example is CurrencyCode. In the domain, the application can use a dedicated type to avoid passing arbitrary strings:

~~~java
public final class CurrencyCode {

    private final String code;

    private CurrencyCode(String code) {
        this.code = code;
    }

    public static CurrencyCode of(String code) {
        if (code == null || code.length() != 3) {
            throw new IllegalArgumentException(
                "Currency code must contain three characters"
            );
        }
        return new CurrencyCode(code.toUpperCase());
    }

    public String value() {
        return code;
    }
}
~~~

Converter:

~~~java
import org.springframework.data.elasticsearch.core.mapping.PropertyValueConverter;

public class CurrencyCodeValueConverter
        implements PropertyValueConverter {

    @Override
    public Object write(Object value) {
        return ((CurrencyCode) value).value();
    }

    @Override
    public Object read(Object value) {
        return CurrencyCode.of((String) value);
    }
}
~~~

Entity:

~~~java
@Field(type = FieldType.Keyword)
@ValueConverter(CurrencyCodeValueConverter.class)
private CurrencyCode currency;
~~~

The document stores currency as a string such as USD, while Java code continues working with CurrencyCode. Currency validation checks stay centralized inside the value object, while the converter simply translates between the two representations.

## 8. Converting Enums or Business States

An enum can be stored by its name, a stable code, or an abbreviated value. Example:

~~~java
public enum OrderStatus {
    CREATED,
    PAID,
    SHIPPED,
    CANCELLED
}
~~~

If storing the enum directly by name, Spring Data may already handle it under default rules. However, when stable codes such as C, P, S, X need to be stored, you can write a custom converter:

~~~java
import org.springframework.data.elasticsearch.core.mapping.PropertyValueConverter;

public class OrderStatusValueConverter
        implements PropertyValueConverter {

    @Override
    public Object write(Object value) {
        OrderStatus status = (OrderStatus) value;
        switch (status) {
            case CREATED:
                return "C";
            case PAID:
                return "P";
            case SHIPPED:
                return "S";
            case CANCELLED:
                return "X";
            default:
                throw new IllegalArgumentException("Unsupported status");
        }
    }

    @Override
    public Object read(Object value) {
        String code = (String) value;
        switch (code) {
            case "C":
                return OrderStatus.CREATED;
            case "P":
                return OrderStatus.PAID;
            case "S":
                return OrderStatus.SHIPPED;
            case "X":
                return OrderStatus.CANCELLED;
            default:
                throw new IllegalArgumentException(
                    "Unknown order status code: " + code
                );
        }
    }
}
~~~

Attach the converter:

~~~java
@Field(type = FieldType.Keyword)
@ValueConverter(OrderStatusValueConverter.class)
private OrderStatus status;
~~~

The benefit of stable codes is that you can rename enum constants in Java without necessarily changing stored data. However, if stored codes change, ensure the converter can still read legacy data or have a document migration plan.

## 9. Null Values and Conversion Errors

A converter must follow the API contract of the Spring Data Elasticsearch version in use. In the current API, read and write receive non-null values and must return non-null values. Therefore:

- Do not write a converter assuming it always handles null inputs.
- Do not return null to signify a failed conversion.
- Define clearly how null properties are handled in the application's mapping.
- If stored data is invalid, raise an error with enough information to locate the offending document and field.

For instance, if a converter expects a string but an old document contains a JSON object, do not silently call toString() and construct a malformed PhoneNumber. Check the data type and raise a clear error.

Across different Spring Data Commons versions, the PropertyValueConverter interface may include generic type parameters and a conversion context or null-handling hooks. Use the exact signature from the Javadoc of the dependency version your project runs. Do not copy signatures from documentation of another version without verifying.

### 9.1. When legacy data no longer shares the same format

Suppose phoneNumber used to store numbers like 0901234567, while the new version stores E.164 format like +84901234567. The new reading converter needs to know how to handle legacy documents.

You can choose one of these approaches:

1. Write reading logic compatible with both formats during a transition period.
2. Reindex or update old documents to the new format.
3. Create a new versioned index, migrate data, and switch aliases after verification.

Do not let the converter guess formats ambiguously. Reading rules must be deterministic and verified with representative data.

## 10. How Do @ValueConverter and ElasticsearchCustomConversions Differ?

Both mechanisms belong to Spring Data Elasticsearch mapping/conversion, but their scopes differ.

| Criterion | @ValueConverter | ElasticsearchCustomConversions |
| --- | --- | --- |
| Scope | Annotated property | By source/target type pair in mapping context |
| Interface | PropertyValueConverter | Spring Converter<S, T> |
| Bidirectional | Single converter with write and read | Usually declared as separate read and write converters |
| Registration | Attach converter class onto property | Register converters in custom conversions |
| Best suited when | Only one or a few properties need a custom format | Every property of that type should share the same rule |

For example, if every CurrencyCode property in the application must convert to a string using the same rule, a global converter may fit better. If only billingCurrency needs a special representation while reportingCurrency uses another rule, @ValueConverter per property is clearer.

Do not register both a global converter and a property converter for the same field without understanding the mapping context's precedence order. When both mechanisms can convert a value, inspect which converter actually executes in your version.

## 11. @ValueConverter and @Field Have Different Responsibilities

@ValueConverter does not do the following:

- Rename a field in Elasticsearch.
- Choose an analyzer or normalizer.
- Choose text, keyword, date, nested, or other mapping types.
- Define dynamic templates.
- Replace index and mapping creation.

Those tasks belong to mapping metadata, @Field, JSON mappings, or Elasticsearch index settings.

Example:

~~~java
@Field(name = "phone_e164", type = FieldType.Keyword)
@ValueConverter(PhoneNumberValueConverter.class)
private PhoneNumber phoneNumber;
~~~

In this snippet:

- name = phone_e164 sets the field name in the document.
- type = FieldType.Keyword selects the mapping type.
- PhoneNumberValueConverter converts the property value.

The three settings work together without replacing one another.

## 12. Impact on Queries

When querying on a property annotated with @ValueConverter, the query value must match the representation of the stored value.

Spring Data Elasticsearch provides the ElasticsearchConverter.updateQuery(query, domainClass) API to update field names and convert query values according to the domain class metadata. When a property has a PropertyValueConverter and a query passes through this mapping flow with the appropriate domain type, Spring Data can convert the query value to its stored form.

Repository example:

~~~java
public interface ContactRepository
        extends ElasticsearchRepository<ContactDocument, String> {

    Optional<ContactDocument> findByPhoneNumber(PhoneNumber phoneNumber);
}
~~~

With PhoneNumberValueConverter, a query method processed through Spring Data infrastructure can use the corresponding E.164 value when building the query for the property.

However, when manually constructing JSON queries in the Elasticsearch Java API Client or sending raw DSL requests directly, the application must supply the value in the exact stored format itself. Do not assume all raw queries go through MappingElasticsearchConverter.

When a query does not return expected results:

1. Read the document's _source to confirm the stored value.
2. Inspect the field mapping.
3. Examine the actual query DSL after Spring Data transformation.
4. Confirm the query uses the right domain class so the property converter can be applied.
5. If calling the low-level client directly, normalize query values to the stored format yourself.

## 13. @ValueConverter Is Not a Jackson Serializer

Jackson serializers/deserializers process JSON according to ObjectMapper configuration. @ValueConverter belongs to Spring Data Elasticsearch mapping metadata and is used by MappingElasticsearchConverter when converting entities to documents and back.

For example:

- @JsonSerialize controls how Jackson serializes a property in a JSON API.
- @JsonDeserialize controls how Jackson builds an object from a JSON API.
- @ValueConverter controls how Spring Data converts a property value when saving to and reading from Elasticsearch.

If the same class serves as both an API request/response DTO and an Elasticsearch document, separate configurations may be required for both pipelines. In larger systems, separating API DTOs from persistence documents typically prevents developers from mistakenly expecting an annotation to work in both places.

## 14. Testing PropertyValueConverter

Converters are small components that can be tested independently without running Elasticsearch.

Bidirectional test example:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class PhoneNumberValueConverterTest {

    private final PhoneNumberValueConverter converter =
        new PhoneNumberValueConverter();

    @Test
    void writesPhoneNumberAsE164String() {
        PhoneNumber phoneNumber = PhoneNumber.of("+84901234567");

        Object storedValue = converter.write(phoneNumber);

        assertEquals("+84901234567", storedValue);
    }

    @Test
    void readsE164StringAsPhoneNumber() {
        Object storedValue = "+84901234567";

        PhoneNumber phoneNumber = (PhoneNumber) converter.read(storedValue);

        assertEquals("+84901234567", phoneNumber.toE164());
    }
}
~~~

Beyond unit tests for the converter, integration tests should verify:

- Entities with the converter are written with the expected value in _source.
- Reading the document reconstructs the correct Java type.
- Other properties without the converter are unaffected.
- Field mappings are compatible with values returned by the converter.
- Derived queries or queries via ElasticsearchOperations use the converted value properly.
- Legacy or invalid data is handled according to the designed rules.

Unit tests verify conversion logic; integration tests verify the converter is actually discovered by Spring Data and invoked during mapping.

## 15. Common Pitfalls

**Using Converter<S, T> instead of PropertyValueConverter.** @ValueConverter requires a class implementing PropertyValueConverter. Standard Spring converters are registered via ElasticsearchCustomConversions.

**Forgetting the read direction.** The entity writes successfully but fails when read back because the converter cannot construct the Java type from the stored value. Implement both write and read.

**Placing the annotation on the wrong property.** The converter only applies to the annotated property. Check that the annotation sits on the field recognized by mapping metadata.

**Assuming the converter applies to all properties of the same type.** @ValueConverter is property-scoped. If you want a global rule, consider ElasticsearchCustomConversions.

**Failing to declare a compatible mapping type.** The converter returns a string while the field is mapped as a number or another type. Pair @ValueConverter with a compatible @Field or JSON mapping.

**Using a converter with dependencies but lacking a suitable constructor.** Regular converter classes require a no-argument constructor with the default factory. If Spring dependencies are needed, configure a factory/registry appropriate for your version.

**Returning null from a converter.** The current API expects non-null input and output values for read/write. Handle nulls per your application's mapping contract.

**Changing the write format while forgetting legacy data.** The new converter may fail to read old documents. Use temporary compatibility logic or migrate/reindex.

**Assuming the converter renames the field.** Field names are determined by @Field(name = "...") or JSON mappings.

**Assuming the converter automatically converts all raw queries.** Queries passing through the mapping converter with domain metadata can be updated; low-level DSL requests must supply stored values manually.

**Putting heavy business logic inside a converter.** A converter should be a small, stable, easy-to-test data transformation.

## 16. Workflow for Implementing @ValueConverter

When a property in a Spring Data Elasticsearch entity needs custom conversion, follow this sequence:

1. Identify the current Java type and the data type you want to store in Elasticsearch.
2. Identify which properties need conversion; if all properties of that type share the same rule, consider global custom conversions.
3. Write a class implementing PropertyValueConverter.
4. Implement write to produce the Elasticsearch value and read to restore the Java type.
5. Ensure the converter satisfies the null and constructor contracts of your Spring Data version.
6. Attach @ValueConverter(ConverterClass.class) to the target field.
7. Declare @Field or JSON mapping to choose a mapping type compatible with the converted value.
8. Test both conversion directions independently.
9. Test saving, reading, and querying through Spring Data.
10. Inspect the actual _source, mapping, and query DSL.
11. Plan compatibility or migration if the storage format changes.

## 17. References

- [Spring Data Elasticsearch - Elasticsearch Object Mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html): role of MappingElasticsearchConverter, mapping annotations, and scope of @ValueConverter.
- [Spring Data Elasticsearch - ValueConverter API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/annotations/ValueConverter.html): how to declare a converter class and constructor requirements.
- [Spring Data Elasticsearch - PropertyValueConverter API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/mapping/PropertyValueConverter.html): read and write contracts.
- [Spring Data Elasticsearch - ElasticsearchConverter API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/convert/ElasticsearchConverter.html): updating field names and query values per mapping metadata.
- [Spring Data Commons - PropertyValueConverterFactory API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/convert/PropertyValueConverterFactory.html): converter instantiation factory, caching, and BeanFactory support.

@ValueConverter has been available since Spring Data Elasticsearch 4.3. API signatures and converter instantiation mechanisms may differ across Spring Data Elasticsearch/Spring Data Commons versions. When implementing, always verify the Javadoc matching your project's exact dependency version.
