# Type Conversion, Date, and Field Naming Errors

In Spring Data Elasticsearch, Java entities are converted into JSON documents according to Spring Data mapping metadata and converters. Meanwhile, Elasticsearch stores and queries data according to the index mapping. If the two sides describe things differently, errors can occur when writing documents, reading responses, filtering by fields, or converting dates.

Three common error groups:

- **Type conversion:** a Java value cannot be converted to the field type in Elasticsearch or vice versa.
- **Date/time conversion:** a date string does not match the format, timezone is ambiguous, timestamp unit is wrong, or precision is lost.
- **Field naming:** the Java property name, the name in JSON _source, the field name in mapping, and the field name in Query DSL are inconsistent.

The proper fix is to inspect all of the entity mapping, converters, actual index mapping, and already indexed data. Changing a Java annotation does not automatically change the mapping type of an existing index.

## 1. Data conversion flow in Spring Data Elasticsearch

When an application saves an entity via ElasticsearchOperations or a repository, Spring Data uses MappingElasticsearchConverter together with mapping metadata to convert the entity into a document. When reading, the converter performs the reverse direction.

~~~text
Java entity
    |
    v
Mapping metadata
(@Document, @Id, @Field, custom conversions)
    |
    v
MappingElasticsearchConverter
    |
    v
JSON document
    |
    v
Elasticsearch mapping
    |
    v
Inverted index / doc values / _source
~~~

When reading:

~~~text
Elasticsearch response
    |
    v
JSON _source + metadata
    |
    v
MappingElasticsearchConverter
    |
    v
Java entity
~~~

Three layers must be distinguished:

1. **Java type:** the property type in the entity, e.g., String, Long, BigDecimal, Instant, or LocalDate.
2. **Elasticsearch field type:** the type in the mapping, e.g., keyword, text, long, scaled_float, date, or date_nanos.
3. **JSON representation:** the actual value in _source, e.g., an ISO-8601 string, epoch millis number, or nested object.

A value can be a string in _source yet parsed and indexed by Elasticsearch as a date. Conversely, a Java property of type Instant does not guarantee the current index already has a matching date mapping.

A repository does not automatically alter an existing mapping just because the entity changed type. The Elasticsearch mapping is an independent storage contract and must be controlled.

## 2. Symptoms indicating conversion or mapping errors

Errors can surface at multiple points in time:

| Timing | Symptom | Common root cause group |
| --- | --- | --- |
| Saving document | mapper_parsing_exception, document_parsing_exception | JSON value is invalid for the field mapping. |
| Saving document | failed to parse field [created_at] | Wrong date format, timezone, or data type. |
| Reading document | ConversionException or converter failure | JSON value cannot be converted to the Java property. |
| Searching | Field not found, empty query results | Wrong field name, field path, or mapping used. |
| Searching via alias | field_caps reports multiple types | Indices behind the alias have inconsistent mappings. |
| Sort/aggregation | Fielddata or incompatible field type | Using text instead of an appropriate keyword/numeric/date field. |
| Startup/index creation | Mapping conflict or index already exists | Entity mapping differs from the active mapping. |

Do not draw conclusions solely from the outermost message. Read the root cause, index name, field name, input value, and actual mapping. A converter-layer error may stem from legacy source data, dynamic mapping, or a custom converter.

## 3. Inspect actual mapping before changing code

The first step when an error occurs is checking how Elasticsearch currently understands the field.

Fetch the index mapping:

~~~http
GET /products/_mapping
~~~

Fetch the mapping of a specific field:

~~~http
GET /products/_mapping/field/created_at
~~~

Fetch document data:

~~~http
GET /products/_doc/P-100
~~~

If you only need to inspect _source:

~~~http
GET /products/_doc/P-100?_source_includes=name,price,created_at
~~~

Questions to answer:

- Does the field exist in the mapping?
- Is the current type keyword, text, long, double, date, or something else?
- Is any date format declared?
- Is the field nested under an object or nested path?
- Do documents contain null values, empty strings, or inconsistent types?
- Which index is being queried when the request goes through an alias?

Do not treat the entity class as sole proof of the mapping. An index may have been created from a template, a migration, or an older application version.

### 3.1. Comparing field capabilities across multiple indices

If searching via an alias or wildcard, indices may define the same field name with different types.

Use the Field Capabilities API:

~~~http
GET /products-*/_field_caps?fields=price,created_at,tenantId
~~~

The response shows which types a field has across the selected indices and which indices have the corresponding mappings. For example, one group of indices may have price as long while another has keyword. Search, sort, or aggregation across the alias may fail due to type conflicts.

If inconsistent mappings are found, handle the old indices via migration/reindex or split aliases by schema version. Changing the Java entity cannot unify mappings of existing indices.

## 4. Type conversion between Java and Elasticsearch

Spring Data Elasticsearch supports converting common Java types to corresponding JSON types and mappings. However, property types should accurately reflect data semantics and Elasticsearch field types.

| Java property | Common Elasticsearch type | Notes |
| --- | --- | --- |
| String for exact match | keyword | Used for term, sort, and aggregation. |
| String for full-text search | text | Has an analyzer; not used directly for typical aggregations. |
| Integer | integer | 32-bit integer range. |
| Long | long | 64-bit integer range. |
| Double | double | Floating-point number. |
| BigDecimal for money | scaled_float or long | Choose based on precision and representation. |
| Boolean | boolean | Avoid sending inconsistent "true"/"false" strings. |
| Instant / Date | date | Standardize format and timezone. |
| Instant needing high precision | date_nanos | Different precision/range limits and cost compared to date. |
| Enum | keyword | Clearly define whether enum name or business code is stored. |

Do not choose a field type simply because it is easy to serialize. Choose based on how the field is searched, sorted, aggregated, and its precision requirements.

### 4.1. Distinguishing text and keyword

A common mistake is declaring a name or status property as text yet running term queries or aggregations as if it were a keyword field.

Example mapping:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      },
      "status": {
        "type": "keyword"
      }
    }
  }
}
~~~

Spring Data entity:

~~~java
@Field(type = FieldType.Text)
private String name;

@Field(type = FieldType.Keyword)
private String status;
~~~

When exact match, sort, or aggregation on name is needed, use the multi-field name.keyword if declared in the mapping. Do not change the query to name.keyword if the actual mapping does not yet have that subfield.

### 4.2. String does not mean every field is keyword

A Java String property can map to text or keyword. Declare it explicitly:

~~~java
@Field(type = FieldType.Keyword)
private String sku;

@Field(type = FieldType.Text)
private String description;
~~~

If dynamic mapping is left to decide, Elasticsearch typically infers the type from the first value. A string may be mapped as text with a keyword subfield under default dynamic templates, but you should not rely on default behavior for critical schemas.

### 4.3. Integers and floating-point numbers

Common mistakes:

- Java Long while the index field is mapped as integer.
- A decimal value sent to an integer field.
- Strings containing thousands separators or decimal commas, which are not valid JSON numbers.
- Some documents sending null, some sending strings, others sending numbers.
- Using Double for monetary values and encountering binary representation errors.

Valid JSON numbers example:

~~~json
{
  "quantity": 12,
  "price": 19.95
}
~~~

Do not send numeric values as strings if the mapping and application contract expect numeric types:

~~~json
{
  "quantity": "12",
  "price": "19,95"
}
~~~

Elasticsearch may support coercion in some scenarios, but you should not rely on coercion to hide inconsistent data. Locale-formatted numbers such as 19,95 should be parsed into numeric types at the application layer before sending.

### 4.4. Currency and BigDecimal

Double can represent decimal numbers only approximately. For money, consider:

- Using long to store the smallest unit, such as cents.
- Using scaled_float with a defined scaling_factor.
- Keeping BigDecimal in the domain layer and converting to an agreed index representation.

Example scaled_float:

~~~json
{
  "properties": {
    "price": {
      "type": "scaled_float",
      "scaling_factor": 100
    }
  }
}
~~~

Entity:

~~~java
@Field(type = FieldType.Scaled_Float, scalingFactor = 100)
private BigDecimal price;
~~~

Enum names and annotation attributes must match the Spring Data version in use. If the application requires strict financial precision, clearly define rounding rules and storage units; scaled_float has quantization semantics based on the scaling factor.

### 4.5. Enums and stored values

If storing enums by name:

~~~java
public enum OrderStatus {
    PENDING,
    PROCESSING,
    COMPLETED
}
~~~

The _source value is typically a string like PENDING, and the mapping is typically keyword. This is readable, but renaming an enum constant can prevent old data from converting.

If an enum has stable business codes, you can use a custom converter to store codes like P, R, C. Make sure the converter can read legacy data during migration periods.

Do not change enum names or codes without a backward-compatibility strategy.

## 5. Dynamic mapping and first-document errors

If an index has no explicit mapping for a field, dynamic mapping can infer the type from the first document containing that field.

Example first document:

~~~json
{
  "price": "19.95"
}
~~~

If the field is inferred as text/keyword, a later document sending a number:

~~~json
{
  "price": 19.95
}
~~~

may cause conflicts or behave unexpectedly.

A similar case happens when the first date field contains a string that does not look like a date. Elasticsearch may map the field as text instead of date. When properly formatted date documents arrive later, the application can encounter mapping conflicts.

How to prevent this:

- Create indices with explicit mappings before ingestion.
- Use index templates for indices created by patterns.
- Use dynamic templates with clear rules.
- Do not let the first document of a field decide the production schema.
- Verify the mapping after creating an index.
- Use strict dynamic mapping if business logic requires detecting fields outside the schema.

Example strict dynamic mapping:

~~~json
{
  "mappings": {
    "dynamic": "strict",
    "properties": {
      "price": {
        "type": "scaled_float",
        "scaling_factor": 100
      },
      "created_at": {
        "type": "date"
      }
    }
  }
}
~~~

With strict mapping, undeclared fields are rejected. This helps catch typos early, but requires the schema and deployment workflow to be thorough.

## 6. Date errors: formats and Java types

Dates are a common source of conversion errors because there are many ways to represent the same point in time:

- ISO-8601 with timezone, e.g., 2026-11-13T08:30:00Z.
- String without timezone, e.g., 2026-11-13 15:30:00.
- Epoch milliseconds, e.g., 1794558600000.
- Epoch seconds, e.g., 1794558600.
- Calendar date without time, e.g., 2026-11-13.

An Elasticsearch date field stores instants numerically and supports parsing declared formats. Elasticsearch does not preserve the original string's timezone as an independent attribute. If business logic needs to know the original timezone, store the zone ID separately.

### 6.1. Choosing Java types by temporal semantics

| Java type | Meaning | When appropriate |
| --- | --- | --- |
| Instant | An instant on the UTC timeline. | Event time, createdAt, updatedAt. |
| OffsetDateTime | An instant with a specific UTC offset. | APIs receiving timestamps with offsets. |
| ZonedDateTime | An instant with a timezone region. | Business logic needing zone rules, e.g., Europe/Paris. |
| LocalDate | A calendar date without time. | Birth date, effective date, holiday. |
| LocalDateTime | Local date and time without zone. | Use only when the domain truly stores local time and has external zone rules. |
| java.util.Date | Instant with millisecond precision. | Legacy code or older APIs. |

For event timestamps, Instant is usually the clearest choice because it carries no implicit timezone assumptions. For calendar dates, LocalDate fits better; do not automatically convert it to a UTC instant unless the domain requires it.

LocalDateTime does not tell you whether 09:00 is in Ho Chi Minh City, London, or Tokyo. Before storing as an Elasticsearch date, the application should determine the zone and convert to Instant or use an explicit date-time contract.

### 6.2. Explicit date mapping

Example entity storing creation time as Instant:

~~~java
import java.time.Instant;
import org.springframework.data.elasticsearch.annotations.DateFormat;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Field(
    name = "created_at",
    type = FieldType.Date,
    format = DateFormat.date_optional_time
)
private Instant createdAt;
~~~

The corresponding Elasticsearch mapping can declare:

~~~json
{
  "properties": {
    "created_at": {
      "type": "date",
      "format": "strict_date_optional_time||epoch_millis"
    }
  }
}
~~~

The exact generated format depends on the annotations and Spring Data version. Inspect the actual mapping after creating the index. Do not assume annotations and manually created mappings are identical.

### 6.3. Custom date patterns

If the source system sends strings in a custom format, you can declare a custom pattern:

~~~java
@Field(
    name = "created_at",
    type = FieldType.Date,
    format = DateFormat.custom,
    pattern = "uuuu-MM-dd HH:mm:ss"
)
private String legacyCreatedAt;
~~~

This example keeps the legacy string as-is to illustrate how Elasticsearch parses a custom format. In a new domain model, normalize strings to Instant after resolving the timezone rather than using String to represent instants. The corresponding mapping must support the exact format sent by the data. If multiple formats must be accepted, Elasticsearch date formats can combine multiple formats separated by double pipes, but you must verify the syntax and pattern of each format.

Example mapping:

~~~json
{
  "properties": {
    "created_at": {
      "type": "date",
      "format": "uuuu-MM-dd HH:mm:ss||strict_date_optional_time||epoch_millis"
    }
  }
}
~~~

Do not add dozens of formats just to mask inconsistent input data. It is better to normalize input at the API/ingestion layer and support only truly necessary formats.

### 6.4. Epoch seconds and epoch milliseconds

A very common mistake is confusing epoch seconds with epoch milliseconds.

Example:

- Epoch seconds: 1794558600
- Epoch milliseconds: 1794558600000

The two values differ by a factor of 1,000. If the field format expects epoch milliseconds but the application sends seconds, the date can fall in 1970 or a completely wrong point in time.

Java conversion:

~~~java
Instant fromSeconds = Instant.ofEpochSecond(epochSeconds);
Instant fromMillis = Instant.ofEpochMilli(epochMillis);
~~~

Do not arbitrarily multiply/divide by 1,000 across multiple layers. Choose one unit contract and document it clearly in the DTO/API.

### 6.5. Timezones and UTC

Example of a timestamp with an offset:

~~~text
2026-11-13T15:30:00+07:00
~~~

This is the same instant as:

~~~text
2026-11-13T08:30:00Z
~~~

Elasticsearch normalizes instants when indexing date fields. If the application needs to display local time, convert Instant to a ZoneId at the presentation layer.

Example:

~~~java
Instant eventTime = Instant.parse("2026-11-13T08:30:00Z");

ZonedDateTime localTime = eventTime.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh")
);
~~~

Do not store a timezone-less LocalDateTime and assume every consumer interprets the same zone. If data is generated across multiple regions, establish a clear convention and also test daylight-saving transitions.

### 6.6. Calendar dates are not timestamps

A birth date of 1995-06-12 is not necessarily an instant at midnight UTC. If the domain concept is a calendar date, use LocalDate and a date-only mapping format:

~~~java
@Field(
    name = "birth_date",
    type = FieldType.Date,
    format = DateFormat.year_month_day
)
private LocalDate birthDate;
~~~

The mapping can use strict_date or an appropriate date pattern. Confirm the generated mapping and test round-trip behavior on the exact version.

If converting a calendar date to Instant, you must decide which zone interprets that date. Otherwise, users in another timezone may see the date shifted by one day upon conversion.

### 6.7. Precision: date and date_nanos

Elasticsearch date stores millisecond precision. If the application needs to preserve nanosecond precision, consider date_nanos.

Example:

~~~java
@Field(
    name = "event_time",
    type = FieldType.Date_Nanos,
    format = DateFormat.date_optional_time
)
private Instant eventTime;
~~~

date_nanos has different range limits and storage characteristics compared to date. Use it only when that precision has business value and Spring Data/client/version support has been verified. Do not assume that because Java Instant holds nanoseconds, Elasticsearch date preserves that same precision.

## 7. Field naming errors between Java, JSON, and Elasticsearch

A Java property can carry a different name in the mapping:

~~~java
@Field(name = "created_at", type = FieldType.Date)
private Instant createdAt;
~~~

The name in Query DSL must be created_at, not createdAt.

Correct query example:

~~~json
{
  "query": {
    "range": {
      "created_at": {
        "gte": "2026-11-01T00:00:00Z"
      }
    }
  }
}
~~~

If the query uses createdAt, Elasticsearch may not find the field or may return empty results, even though the entity property has that name.

### 7.1. @Field(name = ...)

Use @Field(name = "...") to map a property to a specific field name:

~~~java
@Field(name = "customer_id", type = FieldType.Keyword)
private String customerId;

@Field(name = "created_at", type = FieldType.Date)
private Instant createdAt;
~~~

Field names must be consistent across:

- Mapping JSON.
- Query DSL and NativeQuery.
- Sorts and aggregations.
- Scripts accessing doc['field'].
- Ingest pipelines.
- Data export/import.
- Dashboards and other services.

Do not assume Spring Data automatically converts camelCase to snake_case unless a corresponding FieldNamingStrategy is configured.

### 7.2. FieldNamingStrategy

Spring Data Elasticsearch can use FieldNamingStrategy to transform property names by a global rule. Configuration depends on the version and configuration class in use.

Target example:

| Java property | Field name |
| --- | --- |
| customerId | customer_id |
| createdAt | created_at |
| billingAddress | billing_address |

If using a naming strategy, inspect the generated mapping and keep it consistent with all hand-written queries. @Field(name = "...") is useful when a specific name is required or you want to avoid relying on global rules.

Do not change the naming strategy between application versions while old indices are still in use. Doing so can cause new entities to write fields under different names while queries still search the old names.

### 7.3. @Id and _id

A property annotated with @Id maps to Elasticsearch's _id metadata. It is not the same as a regular business field in mapping properties.

Example:

~~~java
@Id
private String id;
~~~

Querying by ID can use the Get API or a term query on _id, depending on the goal. Do not add an extra id field in the mapping and assume it automatically equals _id.

If business logic needs to search by product code, declare a separate property such as sku with type keyword. _id is the document identifier; sku is domain data.

### 7.4. Object and nested paths

For nested objects:

~~~java
public class Address {
    @Field(type = FieldType.Keyword)
    private String city;
}

@Field(type = FieldType.Object)
private Address address;
~~~

The field path can be address.city. If the mapping uses nested type instead of object, queries need a nested query with the right path.

A common mistake is having an object structure in the entity while using the wrong path in queries or assuming object and nested have the same query semantics.

Example mapping:

~~~json
{
  "properties": {
    "address": {
      "type": "object",
      "properties": {
        "city": {
          "type": "keyword"
        }
      }
    }
  }
}
~~~

If nested semantics are required:

~~~json
{
  "properties": {
    "items": {
      "type": "nested",
      "properties": {
        "sku": {
          "type": "keyword"
        }
      }
    }
  }
}
~~~

Nested queries must specify the path items. Simply changing a Java collection to List does not automatically ensure the Elasticsearch mapping is nested; you must declare the proper type.

## 8. @Field, @Transient, and mapping metadata

Annotations affecting mapping must be used consistently:

| Annotation | Effect |
| --- | --- |
| @Document | Declares a managed entity and default index. |
| @Id | Marks the document ID. |
| @Field | Declares field type, name, format, and mapping attributes. |
| @MultiField | Declares a main field along with subfields. |
| @InnerField | Declares a subfield inside a multi-field. |
| @Transient | Excludes the property from persistence mapping/conversion. |
| @WriteOnlyProperty | Write-only property; not read back like a normal field. |
| @ReadOnlyProperty | Read-only property; not written via the corresponding mechanism. |

Annotation names and semantics can vary across versions. Check the Javadoc of the dependency in use if relying on advanced attributes.

### 8.1. @JsonProperty does not replace @Field

Spring Data Elasticsearch uses MappingElasticsearchConverter for entity mapping. Jackson annotations such as @JsonProperty do not automatically replace Spring Data metadata across all write/read paths.

If the same entity is used by both a REST controller and Elasticsearch, two different serialization rules can exist:

- Jackson serializes the DTO/entity for HTTP JSON.
- MappingElasticsearchConverter serializes the entity into an Elasticsearch document.

Do not assume changing @JsonProperty("created_at") will automatically rename all Spring Data queries and mappings. Use @Field(name = "created_at") for Elasticsearch mappings or create separate DTOs if the HTTP contract differs from the persistence contract.

When calling the Elasticsearch Java API Client directly, JsonpMapper is responsible for serializing/deserializing Java Client models. That is also a separate conversion path from MappingElasticsearchConverter.

## 9. Custom conversions for custom data types

When a property uses a custom domain type or legacy format, you can register custom converters.

For example, the domain has LegacyLocalTime, but you want to store it as UTC Instant:

~~~java
public record LegacyLocalTime(LocalDateTime value) {
}
~~~

Writing converter:

~~~java
import java.time.Instant;
import java.time.ZoneOffset;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class LegacyLocalTimeToInstantConverter
        implements Converter<LegacyLocalTime, Instant> {

    @Override
    public Instant convert(LegacyLocalTime source) {
        return source.value().toInstant(ZoneOffset.UTC);
    }
}
~~~

Reading converter:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class InstantToLegacyLocalTimeConverter
        implements Converter<Instant, LegacyLocalTime> {

    @Override
    public LegacyLocalTime convert(Instant source) {
        return new LegacyLocalTime(
                LocalDateTime.ofInstant(source, ZoneOffset.UTC)
        );
    }
}
~~~

This is a specific rule: LocalDateTime is interpreted as UTC. If the actual data belongs to another business timezone, replace ZoneOffset.UTC with the designated ZoneId. Do not use this converter if the domain cannot guarantee that rule.

Register converters via ElasticsearchCustomConversions in configuration:

~~~java
@Bean
@Override
public ElasticsearchCustomConversions elasticsearchCustomConversions() {
    return new ElasticsearchCustomConversions(List.of(
            new LegacyLocalTimeToInstantConverter(),
            new InstantToLegacyLocalTimeConverter()
    ));
}
~~~

The exact method hook may differ depending on the configuration base class and Spring Data version. You can register an ElasticsearchCustomConversions bean if the current configuration supports that bean. After registering, test both writing and reading; a converter working in only one direction can let data save successfully but fail when read back.

### 9.1. Distinguishing reading converters and writing converters

- @WritingConverter applies when converting from the domain type to the storage type.
- @ReadingConverter applies when converting from the storage type to the domain type.

Explicitly marking the conversion direction helps Spring Data select the right converter when multiple types can convert between each other.

Avoid registering overly broad converters, such as String to Object or Number to String, because they can affect many properties unexpectedly. Prefer converters for specific domain types.

### 9.2. Converters do not replace mapping types

Converters determine the values serialized/deserialized. The Elasticsearch mapping determines how fields are indexed, such as keyword, date, numeric, or another type.

For example, a converter turning LocalDateTime into an ISO string does not automatically make the field a date. The field mapping must still declare type date with a format accepting that string.

## 10. Wrong field names in queries, sorts, and aggregations

An entity may save properly yet queries still return wrong results if field paths do not match the mapping.

Example entity:

~~~java
@Field(name = "order_status", type = FieldType.Keyword)
private String status;
~~~

The query must use order_status:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.term(t -> t
                .field("order_status")
                .value("PAID")
        ))
        .build();
~~~

Common mistakes:

- Using status instead of order_status.
- Using createdAt instead of created_at.
- Aggregating on name of type text instead of name.keyword.
- Using address.city when the actual mapping field has a different name.
- Using a nested query for an object field or vice versa.
- A script reading doc['price'] when the real field is unit_price.

Query builders do not automatically infer every field name from Java properties when callers pass field name strings. Keep constants or central field definitions to reduce typos.

Example:

~~~java
public final class ProductFields {

    private ProductFields() {
    }

    public static final String CREATED_AT = "created_at";
    public static final String ORDER_STATUS = "order_status";
    public static final String UNIT_PRICE = "unit_price";
}
~~~

Using constants does not replace checking the mapping, but it helps queries across the codebase use the same field names.

## 11. Existing mapping types cannot be changed directly

Suppose the price field was originally mapped as keyword, then the entity changes to BigDecimal and the annotation declares scaled_float. Elasticsearch cannot change an existing field's type within the same index via a normal mapping update.

A mapping update request with a different type will be rejected. The right solution is creating a new index with the desired mapping and reindexing the data.

Workflow:

1. Create a new index with the new mapping/schema version.
2. Transform legacy data according to defined rules.
3. Reindex or backfill from the appropriate source.
4. Check failed documents and unparseable values.
5. Compare counts, sample values, and query results.
6. Synchronize changes that occurred during migration.
7. Switch read/write aliases to the new index.
8. Keep the old index for a controlled rollback window.
9. Delete the old index once confirmed no callers remain.

Example creating a new index:

~~~http
PUT /products-v2
Content-Type: application/json

{
  "mappings": {
    "properties": {
      "price": {
        "type": "scaled_float",
        "scaling_factor": 100
      },
      "created_at": {
        "type": "date",
        "format": "strict_date_optional_time||epoch_millis"
      }
    }
  }
}
~~~

Do not use mapping updates to try changing keyword to date or text to numeric. Type changes require reindexing or recreating data in a new index.

### 11.1. Transforming bad data during reindex

If the old source contains inconsistent values, you cannot assume reindex will fix them automatically. You may need an ingest pipeline, script, or ETL job to normalize:

- Number strings with locale-specific commas/periods.
- Dates in legacy formats.
- Null values or empty strings.
- Renamed legacy enums.
- Old fields with inconsistent spellings.
- Documents with nested fields differing from the schema.

Store failed documents separately for handling and do not ignore conversion errors without tracking statistics.

## 12. Inspecting data across three layers

When a field does not behave as expected, compare three layers:

| Layer | How to inspect | Question |
| --- | --- | --- |
| Java entity | Check type, annotations, getters/setters, and custom converters. | Does the property have the right type and name? |
| Elasticsearch mapping | GET /index/_mapping or _field_caps. | Does the field have the right type, format, and path? |
| Document source | GET /index/_doc/id. | Is the actual value a number, string, null, or object? |

For example, the Java property is Instant, the mapping is date, yet _source contains a date string without a timezone. When read, the converter may parse it, yet the application still misinterprets the time because the timezone was unspecified.

Another example: Java property is createdAt, mapping is created_at, yet NativeQuery searches createdAt. Both mapping and conversion may be fine; the bug is in the query field name.

Do not fix converters when the real cause is a query using the wrong field name. Layer-by-layer diagnosis avoids unrelated changes.

## 13. Procedure for investigating a conversion error

When receiving an error from production or integration tests, collect:

1. Request type: index, bulk, update, get, or search.
2. Actual concrete index, not just the alias.
3. Document ID or request item ID.
4. Field name reported in the error.
5. Input value with sensitive data masked.
6. Java property type and annotations.
7. Actual mapping of the field.
8. Current _source of the document if available.
9. Root cause and error type in the response.
10. Versions of Spring Data Elasticsearch, Java API Client, and cluster.

Then classify:

- Type mismatch: compare JSON value against mapping type.
- Date parse: compare input against date format and timezone.
- Conversion exception: check custom converter and target Java type.
- Field not found: check naming strategy, @Field(name), and nested path.
- Alias conflict: use field capabilities to identify which index has a different schema.
- Mapping conflict: determine which template or schema version created the index.

## 14. Useful diagnostic APIs

### 14.1. Mapping

~~~http
GET /products/_mapping
~~~

View all field types and formats.

### 14.2. Field mapping

~~~http
GET /products/_mapping/field/created_at,price
~~~

View mappings for specific fields.

### 14.3. Field capabilities

~~~http
GET /products-*/_field_caps?fields=created_at,price,status
~~~

Find mapping conflicts across multiple indices.

### 14.4. Document source

~~~http
GET /products/_doc/P-100
~~~

Compare actual values with Java properties.

### 14.5. Validate query

~~~http
POST /products/_validate/query?explain=true
Content-Type: application/json

{
  "query": {
    "range": {
      "created_at": {
        "gte": "2026-11-01T00:00:00Z"
      }
    }
  }
}
~~~

Validate query helps verify whether a query is valid in syntax and mapping within supported scope. It does not prove the query returns the right business data.

### 14.6. Ingest pipeline simulation

If dates are parsed in an ingest pipeline, you can simulate the pipeline:

~~~http
POST /_ingest/pipeline/_simulate
Content-Type: application/json

{
  "pipeline": {
    "processors": [
      {
        "date": {
          "field": "legacy_created_at",
          "formats": ["yyyy-MM-dd HH:mm:ss"],
          "timezone": "Asia/Ho_Chi_Minh",
          "target_field": "created_at"
        }
      }
    ]
  },
  "docs": [
    {
      "_source": {
        "legacy_created_at": "2026-11-13 15:30:00"
      }
    }
  ]
}
~~~

Simulation helps test date processors and timezones before applying them to real data. Ingest pipeline conversion differs from Spring Data converters; clearly define which layer is responsible for normalization.

## 15. Logging and observability

To investigate conversion issues, log sufficient metadata while avoiding logging entire documents or personal information.

Record:

- Index/alias and concrete index if known.
- Document ID or correlation ID.
- Field name.
- Operation type.
- Error type/status.
- Schema/mapping version.
- Converter name if a custom conversion fails.
- Request ID and timestamp.
- Application version.

Do not log passwords, API keys, tokens, payment data, or full _source in error logs.

In development/test environments, you can raise log levels for Spring Data Elasticsearch or Elasticsearch client packages to inspect requests/responses. Do not enable broad TRACE logging in production because payloads can be large and contain sensitive data.

Monitor metrics:

- Document write failures by error type.
- Date parse failures.
- Conversion exceptions.
- Unusual zero-result search rates after migration.
- Mapping conflicts across index versions.
- Documents dropped from pipelines or sent to dead-letter queues.

## 16. Common anti-patterns

| Anti-pattern | Consequence | How to handle |
| --- | --- | --- |
| Changing only the Java type without recreating the index | Old mapping still retains the old type. | Create a new index and reindex. |
| Letting dynamic mapping decide critical fields | First document may define the wrong type. | Explicit mappings and index templates. |
| Using LocalDateTime as an instant | Implicit timezone and time drift. | Use Instant or explicit ZoneId rules. |
| Confusing epoch seconds with milliseconds | Timestamps off by a huge margin. | Standardize timestamp units. |
| Using Double for money without precision rules | Rounding errors. | BigDecimal in domain and scaled_float/long per contract. |
| Using text for exact match/aggregation | Unsuitable queries or aggregations. | Keyword or multi-field. |
| Using Java property names in manual queries | Field path does not match mapping. | Use Elasticsearch name from @Field(name). |
| Thinking @JsonProperty controls Spring Data mapping | HTTP JSON and Elasticsearch documents may diverge. | Use @Field or converters at the right layer. |
| Overly broad custom converters | Affects many properties unexpectedly. | Converters for specific domain types. |
| Adding many date formats to mask bad input | Data remains inconsistent. | Normalize input and limit supported formats. |
| Ignoring bulk item errors | Part of the data is not written. | Inspect every item and persist failures. |
| Modifying mapping on an alias without checking indices | Indices have differing types. | Use _field_caps and synchronized migration. |
| Reading source via Java API Client and assuming Spring converter ran | Entity may differ from desired mapping. | Distinguish JsonpMapper and MappingElasticsearchConverter. |

## 17. Prevention checklist

Before releasing a new entity or mapping:

1. Do Java property types accurately reflect the domain?
2. Is @Field(type = ...) explicitly declared for important fields?
3. Are field names consistent across @Field(name), mapping, and Query DSL?
4. Is the ID distinguished from business fields?
5. Do date formats match actual input?
6. Do timestamps use seconds or milliseconds?
7. Are timezones clearly defined?
8. Are LocalDate, LocalDateTime, and Instant used with proper semantics?
9. Does date precision require milliseconds or nanoseconds?
10. Do BigDecimal/money fields have scale and rounding rules?
11. Do enums have a stable storage contract?
12. Are custom converters annotated with the proper reading/writing direction?
13. Is the mapping created before ingesting documents?
14. Do all indices in the same alias have consistent mappings?
15. Are there round-trip write/read tests and query tests by field name?
16. Is there a reindex plan when field types need to change?

## 18. References

- [Spring Data Elasticsearch — Object Mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch — Mapping Annotations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/annotated-entities.html)
- [Spring Data Elasticsearch — Custom Conversions](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/custom-conversions.html)
- [Spring Data Elasticsearch — Field Naming Strategy](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Elasticsearch — Mapping](https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping.html)
- [Elasticsearch — Date field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/date.html)
- [Elasticsearch — Date nanos field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/date_nanos.html)
- [Elasticsearch — Field capabilities API](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-field-caps.html)
- [Elasticsearch — Get mapping API](https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-get-mapping.html)
- [Elasticsearch — Reindex API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-reindex.html)

Conversion errors usually originate from mismatches between Java property types, JSON values, and Elasticsearch mappings. For dates, standardize format, epoch unit, timezone, and precision. For field names, use the actual mapping names in queries rather than assuming Java properties and JSON fields match. When an index's mapping type is already wrong, create a new index and reindex with explicit transformation rules; changing annotations will not fix an existing schema.
