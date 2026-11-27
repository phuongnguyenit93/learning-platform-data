# Distinguishing ReadingConverter and WritingConverter

## 1. Role of Converters in Spring Data Elasticsearch

Spring Data Elasticsearch has to convert back and forth between two forms of data:

- **Domain object:** the Java classes used by the application, such as `Customer`, `Address`, `ProductCode`.
- **Elasticsearch document:** the JSON data stored in an index and returned in `_source`.

`MappingElasticsearchConverter` handles mapping Java objects to documents when writing and reading documents into Java objects when retrieving data. During this process, the application can register custom converters to handle business-specific data types.

Two commonly used annotations are:

- `@WritingConverter`: marks a converter used when writing data from an application Java type to a data type that Elasticsearch can store.
- `@ReadingConverter`: marks a converter used when reading data from Elasticsearch's representation back into an application Java type.

The names are defined from the perspective of the storage operation. Writing is the direction where the application writes to Elasticsearch; Reading is the direction where the application reads from Elasticsearch.

## 2. Distinguishing Conversion Directions

Consider an `address` property in a `Customer` entity. In Java, the application uses a custom `Address` type. When saving, we want to convert `Address` into a `Map` so Elasticsearch stores it as a JSON object. When reading, we want to convert the `Map` received from the document back into `Address`.

~~~text
                 WRITE DOCUMENT
Java domain object                         Elasticsearch document
Address  ------------------------------->  Map / JSON object
                 @WritingConverter


                 READ DOCUMENT
Java domain object                         Elasticsearch document
Address  <-------------------------------  Map / JSON object
                 @ReadingConverter
~~~

| Annotation | Conversion Direction | Example Source and Target Types |
|---|---|---|
| `@WritingConverter` | Java domain type → storage type | `Address` → `Map<String, Object>` |
| `@ReadingConverter` | Storage type → Java domain type | `Map<String, Object>` → `Address` |

Two converters typically form a pair so data can travel in both directions. However, having both is not strictly required. If an application only writes a data type without ever reading it back into a domain object, only a writing converter may be needed. If an application only needs to transform returned data into a custom Java type, a reading converter may suffice.

## 3. Example Domain Object Needing Conversion

Suppose an application manages customers. An address has two properties: street and city:

~~~java
public record Address(String street, String city) {
}
~~~

Entity storing the customer:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "customers")
public class Customer {

    @Id
    private String id;

    private String name;

    @Field(type = FieldType.Object)
    private Address address;

    // Constructors, getters and setters
}
~~~

In the business layer, code might create an object:

~~~java
Address address = new Address(
    "2800 East Observatory Road",
    "Los Angeles"
);

Customer customer = new Customer();
customer.setId("c-100");
customer.setName("Alex");
customer.setAddress(address);
~~~

The application wants the document in Elasticsearch to have a readable and queryable JSON structure:

~~~json
{
  "id": "c-100",
  "name": "Alex",
  "address": {
    "street": "2800 East Observatory Road",
    "city": "Los Angeles"
  }
}
~~~

To map `Address` to a JSON object and read it back, we write two converters for the two directions.

## 4. WritingConverter: Converting Domain Objects to Storage Data

A writing converter takes a Java object and returns a type understood by the storage layer. In this example, `Address` is converted into `Map<String, Object>`.

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class AddressToMapConverter
        implements Converter<Address, Map<String, Object>> {

    @Override
    public Map<String, Object> convert(Address source) {
        Map<String, Object> target = new LinkedHashMap<>();

        target.put("street", source.street());
        target.put("city", source.city());

        return target;
    }
}
~~~

Key points to note:

- `@WritingConverter` tells Spring Data this converter is for the write direction.
- The source type is `Address`, the application's domain object type.
- The target type is `Map<String, Object>`, a representation that can be serialized into a JSON object.
- `LinkedHashMap` keeps the entry order consistent when inspecting data, though JSON field order should not be relied upon as a business rule.
- The converter does not send requests to Elasticsearch itself. It only produces the target value for `MappingElasticsearchConverter` to write into the document.

When writing `Customer`, the converter is applied to the `address` property. The `Address` value becomes a map with two keys, `street` and `city`, which is then represented as an object inside `_source`.

Processing flow:

~~~text
Customer
   |
   v
MappingElasticsearchConverter
   |
   v
AddressToMapConverter
   |
   v
Map<String, Object>
   |
   v
JSON object in Elasticsearch document
~~~

If the converter returns a string instead of a map, Elasticsearch receives a scalar value. Therefore, the converter's target type must align with the mapping and data structure expected by the application.

## 5. ReadingConverter: Converting Storage Data to Domain Objects

A reading converter performs the reverse direction. It receives the value provided by the Elasticsearch document and instantiates the Java object used by the application.

~~~java
import java.util.Map;

import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class MapToAddressConverter
        implements Converter<Map<String, Object>, Address> {

    @Override
    public Address convert(Map<String, Object> source) {
        String street = (String) source.get("street");
        String city = (String) source.get("city");

        return new Address(street, city);
    }
}
~~~

Key points to note:

- `@ReadingConverter` marks the read direction.
- The source type is `Map<String, Object>`, representing the object read from the document.
- The target type is `Address`, the domain object type needed by the application.
- The converter extracts fields from the map and constructs an `Address` instance.

Processing flow:

~~~text
Elasticsearch document
   |
   v
Map<String, Object>
   |
   v
MapToAddressConverter
   |
   v
MappingElasticsearchConverter
   |
   v
Customer with Address property
~~~

In this minimal example, the converter assumes `street` and `city` are present and of type `String`. With real-world data, you need to decide how to handle missing fields, null values, or incorrect data types. You can validate inputs and throw a descriptive exception if the document is invalid.

Do not silently assign default values to malformed data if doing so alters business meaning.

## 6. Registering Converters with ElasticsearchCustomConversions

Writing converter classes is not enough. Spring Data needs to know which converters are permitted during mapping. `ElasticsearchCustomConversions` is where custom conversion rules are registered.

A Java configuration based on `ElasticsearchConfiguration`:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;
import org.springframework.data.elasticsearch.core.convert.ElasticsearchCustomConversions;

@Configuration
public class ElasticsearchConfig extends ElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
            .connectedTo("localhost:9200")
            .build();
    }

    @Bean
    @Override
    public ElasticsearchCustomConversions elasticsearchCustomConversions() {
        return new ElasticsearchCustomConversions(
            List.of(
                new AddressToMapConverter(),
                new MapToAddressConverter()
            )
        );
    }
}
~~~

In the configuration above:

1. `ElasticsearchConfiguration` provides the setup mechanism for the Spring Data Elasticsearch client and mapping components.
2. `elasticsearchCustomConversions()` returns the list of custom converters.
3. `AddressToMapConverter` is registered for the write direction.
4. `MapToAddressConverter` is registered for the read direction.
5. `MappingElasticsearchConverter` uses the registered converters when converting between entities and documents.

If the project uses Spring Boot auto-configuration, you can declare an `ElasticsearchCustomConversions` bean in a separate `@Configuration` class following the configuration style of your version. You do not need to create another client just to register converters.

Converters are registered as instances. Spring Data does not automatically scan the entire classpath for every class implementing `Converter`, because auto-registration could introduce unintended conversions into the conversion service. Therefore, add converters to `ElasticsearchCustomConversions` or the corresponding registration mechanism in your project.

`CustomConversions` also includes default converters for common data types, such as Java temporal types. When adding custom converters, use `ElasticsearchCustomConversions` properly so you preserve the default behavior provided by Spring Data.

## 7. Why Distinguish Direction with Annotations?

Spring Data can infer the conversion direction from source and target types. If a converter translates from a domain type to a type Elasticsearch can handle, the system can recognize it as a writing converter. Likewise, a converter from a storage type to a domain type is usually recognized as a reading converter.

However, there are cases where both ends are simple data types that the system can handle directly. In those situations, looking only at source and target is not enough to tell which direction the converter is intended for.

Example:

~~~java
Converter<String, Long>
~~~

`String` and `Long` are both simple data types. If this converter were registered for both directions, Spring Data could apply the conversion in unintended situations. Converting every string into a number when writing is not necessarily what the application intends.

You can specify the direction explicitly with an annotation:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class StringToLongReadingConverter
        implements Converter<String, Long> {

    @Override
    public Long convert(String source) {
        return Long.valueOf(source);
    }
}
~~~

This converter is strictly for the read direction. If you need the reverse write direction, define a separate converter and mark it with `@WritingConverter`:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class LongToStringWritingConverter
        implements Converter<Long, String> {

    @Override
    public String convert(Long source) {
        return source.toString();
    }
}
~~~

Separating the converter pair makes intent clear and prevents one converter from being mistakenly used in both directions.

For custom domain types like `Address`, the conversion direction is usually easier to recognize because one end is the domain type and the other is the storage type. Even so, adding `@ReadingConverter` or `@WritingConverter` remains a clear way to express the converter's purpose.

## 8. Comparison with Bidirectional Converters and Other Annotations

Do not confuse `@ReadingConverter` and `@WritingConverter` with annotations that control reading/writing properties on an entity.

| Component | Meaning |
|---|---|
| `@ReadingConverter` | Marks a `Converter` used when reading data from Elasticsearch into a domain type |
| `@WritingConverter` | Marks a `Converter` used when writing a domain type into storage form |
| `@Transient` | Ignores the property when writing and does not restore that value when reading the entity |
| `@ReadOnlyProperty` | Does not write the property value, but still reads the value from the document |
| `@WriteOnlyProperty` | Writes the property to Elasticsearch, but does not populate the value when reading the entity |
| `@ValueConverter` | Selects a converter scoped to one specific property instead of registering a global conversion for all properties of the same type |

`ReadingConverter` and `WritingConverter` control the direction of a type conversion rule. They do not decide whether a property is allowed to appear in a document. Annotations like `@Transient`, `@ReadOnlyProperty`, and `@WriteOnlyProperty` control whether a property is included during entity reads and writes.

Additionally, a regular converter can be registered globally for all properties of the same type. If only a single property needs special conversion, consider a property-level converter mechanism such as `@ValueConverter` supported in the corresponding Spring Data Elasticsearch version.

## 9. When to Use Custom Converters

Converters are useful when the application's domain model differs from the desired JSON representation in Elasticsearch.

| Case | Writing Converter | Reading Converter |
|---|---|---|
| Value object `Address` to JSON object | `Address` → `Map<String, Object>` | `Map<String, Object>` → `Address` |
| Product code as a custom class | `ProductCode` → `String` | `String` → `ProductCode` |
| Custom currency type | `Money` → `Map` containing amount and currency | `Map` → `Money` |
| Internal status type | Convert enum/domain state to canonical string | Stored string to enum/domain state |

Example with `ProductCode`:

~~~java
public record ProductCode(String value) {
}
~~~

Writing converter:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class ProductCodeToStringConverter
        implements Converter<ProductCode, String> {

    @Override
    public String convert(ProductCode source) {
        return source.value();
    }
}
~~~

Reading converter:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class StringToProductCodeConverter
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        return new ProductCode(source);
    }
}
~~~

The document stores `ProductCode` as a string:

~~~json
{
  "productCode": "SKU-2026-001"
}
~~~

This approach lets the domain model keep the `ProductCode` type to avoid passing raw strings around business logic, while Elasticsearch still stores a simple keyword value.

For data that requires searching or aggregating across multiple attributes, consider converting to a `Map`/object rather than packing everything into one string. For example, if you need to filter separately by amount and currency, storing two distinct fields is better than a single `"USD 12.50"` string.

## 10. Considerations When Implementing Converters

**Register all required directions.** A writing converter does not automatically generate an inverse reading converter. If the application writes and then reads entities, register both directions when needed.

**Target type must match the mapping.** If a converter returns a `Map`, the field in Elasticsearch must have a suitable object mapping. If a converter returns a `String`, choose the matching field type, such as `keyword` or `text` depending on query needs.

**Handle missing and null data.** Legacy documents may omit new fields or have a different structure. Reading converters must define how to handle missing data, nulls, and mismatched types.

**Avoid lossy conversions.** If a writing converter drops a property, the reading converter cannot recover that value from the document. Decide clearly which data is persisted and which exists only in the domain object.

**Avoid overly broad converters.** A converter between two simple types can affect many properties across the system. Use dedicated value object types and directional annotations to limit scope and prevent unintended conversions.

**Do not register duplicate or conflicting converters.** Multiple converters sharing the same source/target types with different rules can make converter selection unpredictable. Each type pair should have one clear conversion meaning.

**Keep converters focused on conversion.** Converters should transform data and perform necessary format checks. Do not place database queries, REST API calls, or business logic depending on external state inside a converter, because mapping can run across many read/write flows.

**Watch out for existing data.** When changing the JSON structure produced by a converter, old documents may no longer be compatible with the new reading converter. You may need to support both the old format during a transition period or reindex the data.

## 11. Complete Write and Read Flow

When the application saves a customer:

~~~text
Customer
  |
  | address: Address
  v
MappingElasticsearchConverter
  |
  v
@WritingConverter: AddressToMapConverter
  |
  v
Map<String, Object>
  |
  v
JSON document
  |
  v
Elasticsearch index
~~~

When the application retrieves a customer:

~~~text
Elasticsearch index
  |
  v
JSON document / _source
  |
  v
Map<String, Object>
  |
  v
@ReadingConverter: MapToAddressConverter
  |
  v
Address
  |
  v
Customer
~~~

Both directions are managed by Spring Data Elasticsearch's mapping mechanism. Services and repositories work with Java entities; the application does not have to invoke converters manually on every save or search operation.

## 12. Workflow for Building and Registering Converters

You can follow this sequence when implementing:

1. Identify which domain types need a different representation in Elasticsearch.
2. Choose an appropriate storage data type: `String`, `Map`, numbers, or another type.
3. Write the write-direction converter from domain type to storage type and annotate it with `@WritingConverter`.
4. Write the read-direction converter from storage type to domain type and annotate it with `@ReadingConverter` if the application needs to reconstruct the entity.
5. Register the instances in `ElasticsearchCustomConversions`.
6. Ensure the custom conversions bean is picked up by the application's `MappingElasticsearchConverter` configuration.
7. Verify that the written JSON document has the correct structure and mapping.
8. Verify that reading data produces valid domain objects, including missing or null fields in cases allowed by business rules.

## Conclusion

`@WritingConverter` and `@ReadingConverter` distinguish the two conversion directions when mapping Java entities to Elasticsearch documents. A writing converter turns a domain type into a storable representation; a reading converter restores the stored representation back into a domain type.

Converters are registered centrally via `ElasticsearchCustomConversions` so `MappingElasticsearchConverter` applies them automatically. Specifying the right source, target, conversion direction, and field mapping ensures data is written consistently, read back with the right type, and keeps the domain model decoupled from the JSON structure stored in Elasticsearch.

## References

- [Spring Data Elasticsearch — Object Mapping and Custom Conversions](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Commons — Custom Conversions](https://docs.spring.io/spring-data/elasticsearch/reference/data-commons/custom-conversions.html)
