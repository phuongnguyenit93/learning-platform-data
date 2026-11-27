# Limitations of Jackson Configuration on Spring Data Mapping

Jackson is a popular library in the Java ecosystem for converting objects to JSON and back. In Spring Boot applications, Jackson is commonly used to parse HTTP requests, produce JSON responses, handle DTOs, and serialize data. Consequently, when an application uses Spring Data Elasticsearch, many developers expect annotations like `@JsonProperty`, `@JsonIgnore`, `@JsonFormat`, or `ObjectMapper` settings to also control how entities are persisted to Elasticsearch.

That expectation does not hold for the normal Spring Data Elasticsearch mapping flow. Spring Data has its own object mapping mechanism, built around mapping metadata and `MappingElasticsearchConverter`. Jackson may appear in the JSON transport layer or in the application's HTTP API, but Jackson configuration does not automatically become Spring Data entity mapping configuration.

Understanding this boundary prevents subtle bugs: a property excluded from API responses with `@JsonIgnore` still getting saved to Elasticsearch; index field names remaining unchanged despite configuring Jackson snake case; or `@JsonFormat` date patterns mismatching the index's date mapping.

## 1. Distinguishing Object Mapping from JSON Serialization

Two tasks are frequently confused:

**Spring Data Elasticsearch object mapping** transforms Java entities into data structures that Spring Data uses to store or query Elasticsearch. This process reads entity metadata, property types, Spring Data annotations, custom conversions, and type mapping information.

**Jackson JSON serialization** transforms Java objects into JSON strings or parses JSON strings into Java objects using `ObjectMapper`, Jackson annotations, modules, naming strategies, and registered serializers/deserializers.

Both mechanisms can coexist in one application while serving different points in the execution flow.

### 1.1. Write flow with Spring Data Elasticsearch

For operations through `ElasticsearchRepository` or `ElasticsearchOperations`, the conceptual flow is:

~~~text
Java Entity
    |
    v
Spring Data Mapping Metadata
    |
    v
MappingElasticsearchConverter
    |
    v
Document / Map representation
    |
    v
Elasticsearch Java API Client
    |
    v
JSON transport mapper
    |
    v
HTTP request to Elasticsearch
~~~

`MappingElasticsearchConverter` is responsible for converting the entity according to Spring Data metadata. Afterward, the Elasticsearch Java API Client sends requests over transport and a JSON-P mapper serializes request structures to JSON. The transport-layer mapper can be backed by Jackson depending on client setup, but it does not replace Spring Data's entity mapping step.

### 1.2. Read flow with Spring Data Elasticsearch

When reading documents through repositories or operations, the flow runs in reverse:

~~~text
HTTP response JSON
    |
    v
Elasticsearch Java API Client / JSON transport mapper
    |
    v
Document / Map representation
    |
    v
MappingElasticsearchConverter
    |
    v
Java Entity
~~~

The JSON transport mapper decodes Elasticsearch's response into client data structures. The Spring Data converter then builds the entity according to metadata, constructors, property accessors, and custom conversions.

### 1.3. Spring MVC's Jackson flow is a separate pipeline

When a controller receives or returns JSON, Spring MVC typically uses a Jackson-based HttpMessageConverter:

~~~text
HTTP request JSON
    |
    v
Jackson ObjectMapper
    |
    v
Request DTO
    |
    v
Controller / Application Service
    |
    v
Spring Data Elasticsearch
    |
    v
Elasticsearch
~~~

On the response path, Jackson serializes the DTO or object returned by the controller into HTTP JSON. Jackson configuration for this API does not automatically govern documents written to Elasticsearch by Spring Data.

## 2. Jackson Annotations Are Not Elasticsearch Mapping Annotations

Jackson annotations describe how Jackson views an object when serializing or deserializing JSON. Spring Data Elasticsearch uses Spring Data's own annotations and metadata to decide how entities are stored.

Common annotations and their boundaries:

| Jackson Annotation / Setting | Purpose in Jackson | How to Control Spring Data Persistence |
| --- | --- | --- |
| `@JsonProperty` | Renames a property in Jackson JSON | Use `@Field(name = "...")` to set the field name in Elasticsearch |
| `@JsonIgnore` | Skips a property when Jackson reads/writes JSON | Use `@Transient` if the property should not be persisted |
| `@JsonFormat` | Controls JSON formatting for date, time, or numeric types | Use `@Field(type = FieldType.Date, format = ..., pattern = ...)` or suitable custom conversions |
| `@JsonInclude` | Controls when Jackson includes a property in JSON | Handle nulls via Spring Data and Elasticsearch mapping/conversion |
| `@JsonSerialize` / `@JsonDeserialize` | Specifies Jackson serializer/deserializer | Use Spring Data custom conversions or property converters |
| `@JsonNaming` | Chooses a naming strategy for Jackson JSON | Set field names via `@Field(name = "...")` or JSON mapping |
| `@JsonView` | Selects property groups during JSON serialization/deserialization | Not a mechanism for selecting fields to store in Elasticsearch |
| `@JsonTypeInfo` | Adds type metadata for Jackson JSON | Use Spring Data type mapping or design explicit field/type metadata |

Do not assume a Jackson annotation will take effect inside a repository just because it works when returning JSON from a controller. Determine whether the object passes through Jackson or `MappingElasticsearchConverter`.

## 3. Example: API JSON Name Differs from Elasticsearch Field Name

Suppose the API needs to return the property display_name, while the index stores a field named product_name:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "catalog-products")
public class ProductDocument {

    @Id
    private String id;

    @JsonProperty("display_name")
    @Field(name = "product_name", type = FieldType.Text)
    private String name;

    // Constructors, getters and setters
}
~~~

In this example:

- Jackson uses display_name when serializing or deserializing the object per Jackson configuration.
- Spring Data Elasticsearch uses product_name as the field name in the persisted document.

The two names can differ because they belong to two different data contracts. Still, think carefully before giving one property two names to avoid confusing the development team. If there is no business reason for the API and index to use different names, adopt a consistent convention.

Merely configuring ObjectMapper with PropertyNamingStrategies.SNAKE_CASE does not mean Spring Data will automatically rename properties to snake case in Elasticsearch. To control persistence field names, declare `@Field(name = "product_name")` or describe the field in JSON mapping.

## 4. Example: @JsonIgnore Does Not Exclude a Property from Elasticsearch

Suppose an entity has an internal field you do not want exposed in the API:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;
import org.springframework.data.elasticsearch.annotations.Document;

@Document(indexName = "catalog-products")
public class ProductDocument {

    private String id;
    private String name;

    @JsonIgnore
    private String internalNote;

    // Constructors, getters and setters
}
~~~

`@JsonIgnore` tells Jackson to skip the property under Jackson rules. However, when saving the entity with `ElasticsearchRepository.save(...)`, the Spring Data converter does not rely on `@JsonIgnore` to decide property persistence. As a result, internalNote can still be written to Elasticsearch.

If the property truly must not be persisted in Elasticsearch, use Spring Data's annotation:

~~~java
import org.springframework.data.annotation.Transient;

@Transient
private String internalNote;
~~~

`@Transient` marks the property as excluded from Spring Data's persistent metadata. Thus, the property is neither written nor read as a regular entity field by the mapping converter.

If asymmetric read/write behaviors are required, you can evaluate `@ReadOnlyProperty` and `@WriteOnlyProperty` per Spring Data Elasticsearch semantics and your version:

- `@ReadOnlyProperty`: property is read from Elasticsearch but not written during normal persistence flows.
- `@WriteOnlyProperty`: property is written to Elasticsearch but not read back into the entity during normal persistence flows.

These annotations serve persistence mapping. They do not replace `@JsonIgnore` if the HTTP API also needs to hide the property. Within an application, you may need both Jackson and Spring Data annotations on the same property—or better yet, separate API DTOs from persistence documents.

## 5. Date Formatting: @JsonFormat and @Field

A common mistake is applying `@JsonFormat` and expecting Elasticsearch to automatically infer the corresponding date mapping:

~~~java
import com.fasterxml.jackson.annotation.JsonFormat;
import java.time.Instant;

@JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss")
private Instant createdAt;
~~~

The annotation above describes how Jackson serializes and deserializes createdAt. It does not define the field's mapping type in Elasticsearch, nor does it ensure date strings are indexed in the desired format.

With Spring Data Elasticsearch, declare the type and format in the mapping:

~~~java
import java.time.Instant;

import org.springframework.data.elasticsearch.annotations.DateFormat;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Field(
    type = FieldType.Date,
    format = DateFormat.date_time
)
private Instant createdAt;
~~~

If a custom format is required, you can use pattern with custom format according to the annotation API of your Spring Data Elasticsearch version:

~~~java
@Field(
    type = FieldType.Date,
    format = DateFormat.custom,
    pattern = "uuuu-MM-dd HH:mm:ss"
)
private Instant createdAt;
~~~

The mapping format must be compatible with the values written by the converter and the data accepted by Elasticsearch. When using Instant, OffsetDateTime, LocalDate, or other temporal types, clearly define the timezone and precision to persist. Do not merely change the API's JSON format and assume the date mapping changed too.

## 6. Jackson Custom Serializers Do Not Replace Spring Data Custom Conversions

Jackson lets you write a serializer to convert a Java type into custom JSON:

~~~java
public class MoneySerializer extends JsonSerializer<Money> {

    @Override
    public void serialize(
            Money value,
            JsonGenerator generator,
            SerializerProvider serializers) throws IOException {

        generator.writeString(value.toPlainString());
    }
}
~~~

If annotated with `@JsonSerialize(using = MoneySerializer.class)`, this serializer is invoked by Jackson during JSON serialization. But when saving an entity with `MappingElasticsearchConverter`, do not expect the Jackson serializer to be called automatically.

To convert a domain type such as Money into an Elasticsearch data type, use Spring Data custom conversions. The example below illustrates converting Money to a string and reading the string back:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class MoneyToStringConverter implements Converter<Money, String> {

    @Override
    public String convert(Money source) {
        return source.toPlainString();
    }
}

@ReadingConverter
public class StringToMoneyConverter implements Converter<String, Money> {

    @Override
    public Money convert(String source) {
        return Money.parse(source);
    }
}
~~~

Register the converters in Spring Data Elasticsearch configuration:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.core.convert.ElasticsearchCustomConversions;

@Configuration
public class ElasticsearchConversionConfiguration {

    @Bean
    ElasticsearchCustomConversions elasticsearchCustomConversions() {
        return new ElasticsearchCustomConversions(List.of(
            new MoneyToStringConverter(),
            new StringToMoneyConverter()
        ));
    }
}
~~~

This example assumes Money exposes toPlainString() and parse() methods. In a real application, use your currency type's actual API and explicitly define currency units, precision, and rounding rules.

Spring Data Elasticsearch also provides `@ValueConverter` when a converter needs to be bound directly to a single property. Custom conversions fit when a domain type has bespoke representation rules or when exact control over written and read types is needed.

Do not use a custom conversion solely to rename a field. Field names belong to mapping metadata and can be declared via `@Field(name = "...")`.

## 7. ObjectMapper Configuration Does Not Control Elasticsearch Mapping

A Spring Boot application may configure Jackson via an ObjectMapper bean, Jackson2ObjectMapperBuilderCustomizer, or spring.jackson.* properties.

Example:

~~~java
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ApiJacksonConfiguration {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer apiJacksonCustomizer() {
        return builder -> builder
            .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
    }
}
~~~

This customizer controls how Spring Boot uses Jackson in applicable JSON pipelines, such as serializing HTTP responses. It does not configure:

- Elasticsearch field names.
- Field types such as text, keyword, date, nested, object, or other types.
- Analyzers, normalizers, doc values, index, or fielddata settings.
- Multi-fields, dynamic templates, or mapping metadata.
- Whether a property is persisted by MappingElasticsearchConverter.
- How Spring Data converts a custom domain type to a storage type.

All of the above must be configured via Spring Data annotations, JSON mappings, custom conversions, or the appropriate Elasticsearch index settings/mappings.

## 8. The Elasticsearch Java Client's JSON Mapper Is a Separate Layer

Modern Spring Data Elasticsearch uses the Elasticsearch Java API Client to communicate with Elasticsearch. This client has a JsonpMapper component to convert Java API Client request/response models to JSON and back.

In certain setups, JsonpMapper may be backed by Jackson via JacksonJsonpMapper. However, distinguish among three components:

1. Spring MVC's ObjectMapper: serves the application's HTTP JSON.
2. Elasticsearch Java API Client's JsonpMapper: serves JSON transport for the API client.
3. Spring Data's MappingElasticsearchConverter: converts persistence entities into document representations and back.

These are three separate roles. Customizing one component does not implicitly alter the other two.

When using repositories or ElasticsearchOperations, the Spring Data converter remains responsible for entity mapping per metadata. When calling the Java API Client directly with a client request model or low-level JSON payload, JsonpMapper can participate in serializing and deserializing data at the client layer. Exact behavior depends on the API invoked and how the client is configured.

Therefore, if a Jackson annotation fails to take effect in ElasticsearchRepository.save(...), changing Spring MVC's ObjectMapper will generally not fix the root cause. Identify which converter the object goes through before adjusting configuration.

## 9. Spring Data Mechanisms to Use for Persistence Mapping

Spring Data Elasticsearch has dedicated annotations and APIs for needs commonly confused with Jackson.

| Need | Spring Data Elasticsearch Mechanism |
| --- | --- |
| Choose index for an entity | `@Document(indexName = "...")` |
| Mark document ID | `@Id` |
| Rename stored field | `@Field(name = "...")` |
| Choose Elasticsearch field type | `@Field(type = FieldType...)` |
| Set date format and pattern | `@Field(format = ..., pattern = ...)` |
| Declare multi-fields | `@MultiField` and `@InnerField` |
| Exclude property from persistence mapping | `@Transient` |
| Read-only or write-only property | `@ReadOnlyProperty`, `@WriteOnlyProperty` |
| Custom Java type conversion | `ElasticsearchCustomConversions` or `@ValueConverter` |
| Control type aliases | `@TypeAlias` and type mapper configuration |
| Declare JSON mapping | `@Mapping` or index management APIs |
| Declare index settings | `@Setting` or index management APIs |

### 9.1. Entity example using the right annotation for each goal

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.elasticsearch.annotations.DateFormat;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

import java.time.Instant;

@Document(indexName = "catalog-products")
public class ProductDocument {

    @Id
    private String id;

    @JsonProperty("display_name")
    @Field(name = "product_name", type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Date, format = DateFormat.date_time)
    private Instant createdAt;

    @JsonIgnore
    @Transient
    private String internalNote;

    // Constructors, getters and setters
}
~~~

In this example:

- @JsonProperty serves Jackson's JSON contract.
- @Field serves field name and type in Elasticsearch.
- @Field with type Date and format describes the date mapping.
- @JsonIgnore hides the property in Jackson flows.
- @Transient excludes the property from Spring Data's persistent mapping.

If API and persistence requirements differ significantly, consider using separate ProductRequest, ProductResponse, and ProductDocument classes instead of stacking annotations from both systems onto a single class.

## 10. Constructors, Property Access, and Type Metadata

Jackson provides its own mechanisms such as JsonCreator, JsonProperty on constructor parameters, and JsonTypeInfo. Those annotations do not configure how Spring Data instantiates an entity from a document.

Spring Data relies on mapping metadata, persistence constructors, and property accessors. When you need to specify the constructor used to instantiate an entity from stored data, use persistence annotations such as PersistenceCreator according to your Spring Data version.

Example:

~~~java
import org.springframework.data.annotation.PersistenceCreator;

public class ProductSummary {

    private final String sku;
    private final String name;

    @PersistenceCreator
    public ProductSummary(String sku, String name) {
        this.sku = sku;
        this.name = name;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }
}
~~~

Spring Data Elasticsearch also has its own type hint mechanism. The mapping converter can store type information, typically in a _class field, to help restore the concrete type when reading objects declared with a general type. `@TypeAlias` lets you define a shorter alias for a type. This is a Spring Data type mapping mechanism; do not treat JsonTypeInfo as a replacement.

If you need to customize how type hints are stored, look into Spring Data Elasticsearch's type mapper and mapping context. Changing type metadata can affect the ability to read legacy data, so manage it as a schema change.

## 11. Maps, Nested Objects, and Dynamic Fields

Jackson has annotations such as JsonAnyGetter, JsonAnySetter, or JsonUnwrapped to control how JSON objects are read and written. They do not replace Elasticsearch mapping rules.

If a document contains extensible attributes, Spring Data can map Map<String, Object> according to property mapping metadata and actual runtime types:

~~~java
import java.util.Map;

import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Field(type = FieldType.Object)
private Map<String, Object> attributes;
~~~

Elasticsearch still decides how child fields are indexed via object mappings, dynamic mapping, and dynamic templates. Jackson's JsonAnySetter does not create dynamic templates, enforce dynamic strict mode, or decide whether a child string becomes text or keyword.

If child objects need nested document behavior, declare FieldType.Nested or the equivalent JSON mapping. If child fields should not be indexed, design appropriate mappings and dynamic modes. These are Elasticsearch schema decisions, not JSON serialization decisions.

## 12. Mapping JSON and Jackson JSON Are Not the Same Thing

Spring Data Elasticsearch supports using a JSON mapping file to declare index schemas. Example:

~~~java
@Document(indexName = "catalog-products")
@Mapping(mappingPath = "/elasticsearch/mappings/product-mapping.json")
public class ProductDocument {
    // Entity properties
}
~~~

The JSON mapping file describes settings or mappings following Elasticsearch's API structure, such as properties, dynamic_templates, analyzers, fields, and types. This file is not a Jackson ObjectMapper configuration.

A mapping might declare:

~~~json
{
  "properties": {
    "product_name": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword"
        }
      }
    },
    "created_at": {
      "type": "date",
      "format": "strict_date_optional_time||epoch_millis"
    }
  }
}
~~~

This mapping governs how Elasticsearch indexes and queries fields. Jackson may serialize an object into JSON with different property names, yet that does not alter the mapping created inside the index.

## 13. Inspecting the Right Layer When Configuration Has No Effect

When data stored in Elasticsearch differs from expectations, pinpoint the exact step causing the discrepancy.

### 13.1. Inspect the index mapping

Read the actual mapping:

~~~http
GET /catalog-products/_mapping
~~~

Verify field names, data types, multi-fields, date formats, analyzers, nested/object settings, and dynamic templates. If field names are wrong, check Field names or JSON mappings.

### 13.2. Inspect the stored document

Read the document's _source:

~~~http
GET /catalog-products/_doc/sku-1001
~~~

Check which fields were actually written, their names, value types, and content. If a property is still saved despite JsonIgnore, check whether the save went through MappingElasticsearchConverter and whether the property is marked Transient.

### 13.3. Inspect API JSON separately

If an HTTP response lacks a property or has the wrong property name, inspect ObjectMapper, Jackson annotations, and Spring MVC configuration. Do not infer directly from API JSON output that Elasticsearch's _source shares the exact same structure.

### 13.4. Inspect custom conversions

If a Java type is stored in an unexpected form, check:

- Whether Spring Data has a default converter for that type.
- Whether ElasticsearchCustomConversions or ValueConverter is actively applied.
- Whether read and write converters are symmetric in format.
- Whether the Elasticsearch mapping has a type compatible with what the converter produces.

Reading the actual document and mapping usually reveals whether an issue lies in entity conversion, schema configuration, or the API JSON layer.

## 14. Class Design: Share One Class or Separate DTO and Document?

A single class can carry both Jackson and Spring Data annotations, though doing so binds two contracts to the same type. When the API and persistence layers have different lifecycles, separating classes is usually easier to maintain.

Example:

~~~text
ProductRequest
    |
    v
ProductApplicationService
    |
    v
Product (domain model)
    |
    v
ProductDocument (Elasticsearch persistence)
    |
    v
ElasticsearchRepository

ProductResponse
    ^
    |
ProductApplicationService
~~~

Each type has a clear responsibility:

- ProductRequest: data structure received from clients; uses Jackson to parse JSON.
- Product: business representation; need not depend on Jackson or Elasticsearch without good reason.
- ProductDocument: representation of data stored in the index; uses Spring Data annotations and conversions.
- ProductResponse: JSON structure returned to clients; uses Jackson to serialize per the API contract.

Benefits of separation:

- Field names in the index can change without breaking the public API.
- Internal data can be hidden from responses while still persisted when needed.
- Elasticsearch can be swapped for another storage system with minimal impact on the domain.
- Mapping schemas and API schemas can be versioned independently.
- Avoids stacking conflicting annotations on the same property.

For small applications with simple schemas, sharing a single class may still be practical. In that case, stay aware of which annotations affect Jackson and which affect Spring Data.

## 15. Common Pitfalls and Fixes

**Using JsonProperty to rename an Elasticsearch field.** This annotation controls Jackson. Use Field name or JSON mapping to rename persistence fields.

**Using JsonIgnore to omit data from _source.** Jackson may omit the property in JSON responses, yet Spring Data converter still persists it. Use Transient or separate DTOs from documents.

**Using JsonFormat to fix date mapping errors.** Jackson formatting does not define Elasticsearch's date format. Declare FieldType.Date, format, and pattern in the mapping or use an appropriate converter.

**Changing ObjectMapper while repositories still write the same data.** Repositories use Spring Data's mapping converter. Configure annotations, custom conversions, or mapping metadata at the persistence layer.

**Using a Jackson custom serializer to transform domain types.** Serializers only execute in Jackson flows. Use ElasticsearchCustomConversions or ValueConverter for persistence.

**Using JsonNaming to apply snake case to mappings.** Jackson naming strategies do not rename Spring Data fields. Declare Field names or JSON mappings.

**Using JsonTypeInfo to alter _class.** Spring Data type hints have their own mechanism. Look into TypeAlias and type mappers.

**Assuming a correct API response means the document is also correct.** The response may have been transformed by Jackson after reading the entity. Inspect _source and mappings directly in Elasticsearch.

## 16. Workflow for Choosing the Right Mechanism

When changing how data is represented, start from the goal:

1. To rename properties in HTTP requests or responses, use Jackson annotations or ObjectMapper configuration.
2. To rename fields in Elasticsearch, use Field name or JSON mapping.
3. To exclude a property from persistence, use Transient; to only hide it in the API, use Jackson or a separate response DTO.
4. To change an Elasticsearch field type or format, configure Field, JSON mapping, or custom conversions.
5. To convert a domain Java type into another storage form, register ElasticsearchCustomConversions or ValueConverter.
6. To change how type hints are stored, examine Spring Data's TypeAlias and type mapping.
7. If calling the Java API Client directly, determine whether JsonpMapper participates in serializing/deserializing request/response models.
8. After making changes, inspect both the actual mapping and _source; check HTTP responses separately if the API is also affected.

Jackson is an essential tool in Spring applications, but it is not Spring Data Elasticsearch's entity mapping mechanism. MappingElasticsearchConverter together with Spring Data metadata governs how entities become documents and get restored from documents. Keeping these two pipelines distinct lets you pick the right annotations, converters, and configurations for each goal without accidentally breaking data contracts in another layer.
