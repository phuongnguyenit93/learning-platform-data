# Java Object to Document Conversion and Reverse Reading Workflow

Spring Data Elasticsearch helps applications work with Elasticsearch documents using Java objects. When saving an entity, the framework converts Java properties into a document structure suitable for the index. When reading results, the framework converts document data back into the Java type requested by the application.

The central component of this process is MappingElasticsearchConverter. The converter uses entity metadata, mapping annotations, and the custom conversions system to determine field names, data types, how nested objects are handled, and how values are restored when reading.

Understanding the conversion flow helps explain why a Java property can become an Elasticsearch field with a different name, why the ID does not reside in the JSON source, why date and time types require clear conventions, and how to extend the converter when dealing with custom business data types.

## 1. Java Object, Document, and Elasticsearch _source

Three concepts are frequently mentioned when converting data:

- **Java object:** an in-memory object, such as Product or Order.
- **Spring Data Document:** a map-like document structure that Spring Data uses in the conversion and data manipulation layer.
- **Elasticsearch _source:** the JSON content stored for a document in an index, usually containing business fields.

Java object example:

~~~java
public class Product {

    private String id;
    private String name;
    private BigDecimal price;
    private List<String> tags;

    // constructors, getters and setters
}
~~~

The logical document may have a similar structure:

~~~json
{
  "name": "Mechanical Keyboard",
  "price": 89.90,
  "tags": ["keyboard", "peripheral"]
}
~~~

When written to Elasticsearch, this business content usually becomes the _source section. A document also has metadata managed by Elasticsearch, such as _id, routing, version, or sequence number information. That metadata does not necessarily reside inside the JSON _source.

Therefore, you should not equate the entire Elasticsearch hit with the _source section. A search hit may contain:

~~~text
SearchHit
  ├── _index
  ├── _id
  ├── _score
  ├── _routing (if present)
  └── _source
        ├── name
        ├── price
        └── tags
~~~

Spring Data coordinates the converter with the Elasticsearch access layer to map both entity data and the necessary metadata.

## 2. Role of MappingElasticsearchConverter

MappingElasticsearchConverter is the component that converts between Java objects and Documents. It operates based on Elasticsearch mapping metadata, typically provided via ElasticsearchMappingContext.

The main components can be visualized as follows:

~~~text
Java entity
    |
    v
ElasticsearchMappingContext
    |
    | describes entity, properties, annotations
    v
MappingElasticsearchConverter
    |
    | writes object to Document
    | reads Document to object
    v
Spring Data Document
    |
    v
ElasticsearchOperations / Repository
    |
    v
Elasticsearch Java Client
    |
    v
Elasticsearch index
~~~

MappingElasticsearchConverter is responsible for converting data according to metadata. ElasticsearchOperations or the repository is responsible for performing save, get, search operations, and connecting to Elasticsearch.

Do not treat the converter as a general-purpose JSON serializer. It understands Spring Data Elasticsearch metadata such as @Id, @Field, @Document, entity structure, and registered custom converters. This differs from using Jackson to serialize a DTO for a REST API.

### 2.1. ElasticsearchMappingContext

The mapping context holds mapping information for entities managed by Spring Data:

- The name and type of the entity.
- Which property is the ID.
- The corresponding Elasticsearch field name.
- The field type declared via @Field.
- Nested object and collection structures.
- Metadata needed for instantiating and reading the entity.

The mapping context is built from Java classes and annotations. When the converter processes Product, it can know that id is the ID, name is text, category is keyword, or that a property is renamed using @Field(name = "...").

### 2.2. Custom conversions

Custom conversions allow the application to specify how a custom business type is converted into a type that Elasticsearch can store, and how that type is restored when reading.

For example, an EmailAddress type can be stored as a keyword string. The writing converter extracts the string value; the reading converter reconstructs the EmailAddress from that string.

## 3. Declaring Entities and Mapping Metadata

Let's start with an entity that has explicit metadata:

~~~java
import java.math.BigDecimal;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(type = FieldType.Keyword)
    private List<String> tags;

    // constructors, getters and setters
}
~~~

Metadata determines how the converter processes each property:

| Java Property | Metadata | Conversion Meaning |
|---|---|---|
| id | @Id | Maps to the Elasticsearch document ID |
| name | FieldType.Text | Stores text value for full-text search |
| category | FieldType.Keyword | Stores exact value for filtering or aggregation |
| price | FieldType.Double | Converts numeric value to an appropriate numeric type in the document |
| tags | FieldType.Keyword | Converts collection into a list of keyword values |

The @Field annotation controls the field mapping. The converter is responsible for writing the corresponding Java value into the Document. Whether a field has type text or keyword mainly affects Elasticsearch's mapping and search behavior; it does not mean the converter itself performs linguistic analysis on the string.

If certain metadata is not declared, Spring Data can infer the mapping based on the Java type and default rules. For fields important for searching, filtering, or sorting, it is best to declare them explicitly so the data contract is clear and stable.

## 4. Write Flow: Java Object to Document

When calling repository.save(product) or ElasticsearchOperations.save(product), Spring Data executes a conceptual sequence of steps.

### 4.1. Receive the entity and determine metadata

The application passes the Product object into the repository or operations layer. Spring Data identifies the entity type, reads the corresponding metadata from the mapping context, and finds the target index information from @Document.

Example:

~~~java
Product product = new Product();
product.setId("product-100");
product.setName("Mechanical Keyboard");
product.setCategory("peripherals");
product.setPrice(new BigDecimal("89.90"));
product.setTags(List.of("keyboard", "office"));

productRepository.save(product);
~~~

The repository knows that the Product entity corresponds to the products index. The ID and field mappings are retrieved from metadata.

### 4.2. Traverse properties and convert values

The converter reads each persistent property and converts its value:

- The ID property is handled as the document ID.
- Simple types such as String, Boolean, and numbers are converted to their corresponding values.
- Enums are converted according to configured conversion rules.
- Date/time types are converted according to supported converters and Java types.
- Collections are converted into lists of values or lists of objects.
- Maps are converted into appropriate key/value structures.
- Nested objects are converted into nested sub-document structures.
- Custom converters are applied when the property type has a registered conversion.

If a property has a field name different from the Java property name, metadata instructs the converter to write to the configured field name.

### 4.3. Build the Document

For the example entity, the source section may look like:

~~~json
{
  "name": "Mechanical Keyboard",
  "category": "peripherals",
  "price": 89.90,
  "tags": ["keyboard", "office"]
}
~~~

The id value is typically used as the document's _id in Elasticsearch and does not necessarily appear in _source. When retrieving the ID from results, the mapping and operations layers combine the hit metadata to assign it back to the @Id property.

### 4.4. Send the request to Elasticsearch

Once the Document is built, the operations layer uses the target index and relevant metadata to construct the write request. Elasticsearch receives the document, applies the index mapping, and indexes the data.

This means there are two layers of rules:

- Spring Data mapping determines how a Java object is converted into document data.
- Elasticsearch mapping determines how Elasticsearch interprets, indexes, and queries each field.

The two layers must be compatible. The converter might write a JSON value, yet Elasticsearch can still reject it if that value does not match the mapping—for instance, a date string in the wrong format or an object incompatible with the declared field type.

## 5. Read Flow: Document to Java Object

When the application retrieves a document by ID or performs a search, Elasticsearch returns hits. Each hit contains metadata and a source section. Spring Data uses the mapping context together with the converter to instantiate an object of the type requested by the application.

### 5.1. Retrieve data from Elasticsearch

Example using a repository:

~~~java
Optional<Product> result = productRepository.findById("product-100");

result.ifPresent(product -> {
    System.out.println(product.getName());
    System.out.println(product.getPrice());
});
~~~

Or using ElasticsearchOperations when you need to specify the index explicitly:

~~~java
Product product = operations.get(
        "product-100",
        Product.class,
        IndexCoordinates.of("products")
);
~~~

Exact API signatures may vary across release trains; use the overload available in your project's Spring Data Elasticsearch version.

### 5.2. Read source and metadata

Elasticsearch returns _source along with hit metadata. The Spring Data layer creates a Document structure for the converter and provides the ID or other metadata according to the corresponding API.

The converter cannot infer all Java types solely from JSON. It needs the target type Product and mapping metadata to know how to construct the object.

### 5.3. Instantiate the target object

MappingElasticsearchConverter reads each field:

- Finds the persistent property matching the field name.
- Converts the data type from the Document value to the Java type.
- Creates nested objects and collections if present.
- Restores the ID property from document metadata.
- Applies a custom reading converter if the property type requires it.
- Instantiates the entity via a constructor or property access mechanism matching the metadata.

The result is a Java object that the application can continue using:

~~~text
Elasticsearch hit
      |
      v
Document source + metadata
      |
      v
MappingElasticsearchConverter
      |
      | look up Product metadata
      | convert each field
      | build nested objects
      | restore ID
      v
Product Java object
~~~

## 6. Field Name and ID Mapping

### 6.1. Renaming fields

A Java property name does not have to match the Elasticsearch field name. You can use the name attribute of @Field:

~~~java
@Field(name = "product_name", type = FieldType.Text)
private String name;
~~~

When writing, the converter uses product_name as the field name in the Document. When reading, the converter looks for product_name and assigns the value to the name property.

This is useful when an API or index already follows a snake_case convention while Java code uses camelCase.

### 6.2. ID as separate metadata

The property annotated with @Id is used by Spring Data as the Elasticsearch document ID. The ID helps locate the document for get, update, and delete operations.

Example:

~~~java
@Id
private String id;
~~~

The ID does not need to be repeated in _source if the application only needs it as document identity. If business logic also needs to query the ID like a regular field, you can store an additional data property or design an appropriate field, while avoiding confusing a business field with the _id metadata.

If the entity does not yet have an ID, ID generation behavior depends on the operation and API used. Elasticsearch can generate an ID for index operations where no ID is specified; the application should verify how the ID is returned and assigned back to the entity in the Spring Data version in use. For standard CRUD repositories, it is best to define a clear ID strategy rather than relying on assumptions about null values.

## 7. Converting Nested Objects and Collections

An Elasticsearch document can contain nested objects. The Spring Data converter can convert object and collection types into corresponding structures.

Example:

~~~java
public class Manufacturer {

    private String name;
    private String country;

    // constructors, getters and setters
}

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    private String name;

    private Manufacturer manufacturer;

    private List<String> tags;

    // constructors, getters and setters
}
~~~

The document source may have this structure:

~~~json
{
  "name": "Mechanical Keyboard",
  "manufacturer": {
    "name": "Example Devices",
    "country": "VN"
  },
  "tags": ["keyboard", "office"]
}
~~~

When reading, the converter constructs Manufacturer and the list of tags from the sub-structures. When writing, the converter traverses the child object and converts its properties into nested maps.

### 7.1. Object and nested are two different concepts

In Elasticsearch, an object field and a nested field have different querying behavior. If a field is object, inner values may be flattened during indexing. With an array of objects, querying multiple conditions can accidentally match properties belonging to different elements.

The nested type preserves the boundaries of each sub-object so nested queries are more accurate, at the cost of its own storage and query overhead.

You can declare:

~~~java
@Field(type = FieldType.Nested)
private List<OrderLine> lines;
~~~

The converter transforms the Java structure into a nested document; the Elasticsearch mapping defines that field as nested. Only use FieldType.Nested when query requirements need nested semantics. Having a List of objects does not mean you always have to choose nested.

## 8. Common Data Types and Conversions

Several Java types are commonly mapped as follows:

| Java Type | Typical Document Value | Notes |
|---|---|---|
| String | String | Text or keyword mapping determines how it is indexed |
| Boolean | true/false | Uses a boolean field |
| Integer, Long | Integer number | Choose a numeric type fitting the value range |
| Double, BigDecimal | Number | Consider precision and numeric mapping |
| Enum | Enum representation per conversion | Standardize whether to store the name or a business code |
| Instant | Timestamp | Choose date or date_nanos depending on precision |
| LocalDate | Calendar date | Distinguish calendar date from an absolute instant |
| Collection | Array of values or objects | Field mapping must match the content |
| Map | Key/value object | Control key structure and value types |

The converter transforms Java types into values that Document can represent. Elasticsearch mapping then determines how those values are stored and queried. For instance, BigDecimal can be converted into a numeric value, yet calculation precision and numeric mapping type still need to be designed appropriately for currency operations.

## 9. Custom Conversions for Domain-Specific Types

Not every Java type can be converted properly using default rules. When you have custom types such as EmailAddress, Money, PhoneNumber, or a value object, you can register writing and reading converters.

Value object example:

~~~java
public record EmailAddress(String value) {
}
~~~

Writing converter:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class EmailAddressWritingConverter
        implements Converter<EmailAddress, String> {

    @Override
    public String convert(EmailAddress source) {
        return source.value();
    }
}
~~~

Reading converter:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class EmailAddressReadingConverter
        implements Converter<String, EmailAddress> {

    @Override
    public EmailAddress convert(String source) {
        return new EmailAddress(source);
    }
}
~~~

When writing, EmailAddress is converted into a string. When reading, the string is converted back into EmailAddress. The field can be declared as keyword if the application needs filtering or exact matching:

~~~java
@Field(type = FieldType.Keyword)
private EmailAddress email;
~~~

### 9.1. Registering custom conversions

Spring Data Elasticsearch provides ElasticsearchCustomConversions to register additional converters. How the bean is declared may differ slightly across versions and application configurations, but the idea is to supply a list of converters to the mapping infrastructure:

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
                new EmailAddressWritingConverter(),
                new EmailAddressReadingConverter()
        ));
    }
}
~~~

Check the package, constructor, and how Spring Boot detects the bean for your project's release train. Converters must be registered into the right Elasticsearch converter infrastructure; merely creating a Converter class without registering it does not guarantee it will be used.

### 9.2. When should you use a custom converter?

Use a custom converter when:

- A business type has no suitable default representation.
- You want explicit control over the write and read format.
- You need to maintain compatibility with legacy data.
- You want to standardize a value object in one place instead of duplicating logic in services.

Do not write converters for every simple data type if Spring Data already supports it well. Each converter is part of the data contract and must be tested in both directions.

## 10. Constructors, Property Access, and Entity Immutability

Reading a Document into a Java object is not just setting individual fields after invoking a no-arg constructor. Spring Data has entity instantiation and property population mechanisms based on metadata.

For an entity with an appropriate constructor, Spring Data can use the constructor to instantiate the object from the read values. This supports immutable classes or value objects. Constructor parameter names, metadata, and property access mechanisms must align with the project's mapping configuration.

Example:

~~~java
@Document(indexName = "products")
public class ProductSummary {

    @Id
    private final String id;

    private final String name;

    public ProductSummary(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

In practice, ensure Spring Data has enough metadata to bind document values to constructor parameters. When using Lombok, records, or multi-argument constructors, verify how the compiler retains parameter names and the mapping rules of the version in use.

Do not arbitrarily change constructors or property names once data has been persisted long-term. A change in the entity can alter how old documents are read, even though the data in Elasticsearch has not changed.

## 11. Type Hints and Target Type When Reading

A JSON document does not always contain enough information to restore the exact original Java type. For example, a property declared as an interface may accept multiple different implementations. Spring Data can use type information in the document to know the concrete type when reading.

In some configurations, a type hint can be written under a metadata field like _class. Type mapping and alias mechanisms can be customized. If the application disables type hints or stores documents from another system without Java type metadata, you should read into a concrete target type or define custom rules to determine the subtype.

Do not treat _class as a business field or use it as an authorization mechanism. It is metadata for mapping purposes and needs careful consideration when sharing an index across multiple applications or multiple model versions.

## 12. SearchHit, SearchHits, and Converted Objects

When searching, Spring Data can return SearchHits<T> instead of just a list of entities. Each SearchHit<T> contains the entity constructed by the converter along with search metadata such as score, ID, index, and routing if present.

Illustrative example:

~~~java
SearchHits<Product> searchHits =
        operations.search(
                query,
                Product.class,
                IndexCoordinates.of("products")
        );

for (SearchHit<Product> hit : searchHits) {
    Product product = hit.getContent();

    System.out.println(product.getName());
    System.out.println(hit.getScore());
    System.out.println(hit.getId());
}
~~~

Query creation and search method signatures may vary across Spring Data Elasticsearch versions. The key takeaway is that the hit content has already been converted into Product, while score and certain other details live on the SearchHit class.

If you only need a list of entities, the application can use utility APIs to convert SearchHits into a content list. When you need relevance, highlights, sort values, or metadata, retain SearchHits so search result information is not lost.

## 13. How Does Mapping Converter Differ from Jackson JSON Serialization?

Both mechanisms can produce JSON or transform data, but their goals differ:

| Criterion | MappingElasticsearchConverter | Jackson ObjectMapper |
|---|---|---|
| Purpose | Converts Spring Data entities to Elasticsearch Documents and reads them back | General-purpose JSON serialization/deserialization |
| Metadata | Uses @Document, @Id, @Field, and mapping context | Uses Jackson annotations and modules |
| Index target | Combines entity metadata with operations | Has no built-in awareness of Elasticsearch indices |
| Elasticsearch ID | Spring Data layer coordinates ID metadata | Usually just processes JSON properties per configuration |
| Field mapping | Can reflect Elasticsearch field types | Does not design index mappings itself |
| Custom conversion | ElasticsearchCustomConversions and conversion infrastructure | Jackson serializers/deserializers |

If a controller returns Product as an HTTP JSON response, the application can use Jackson. If Product is saved to Elasticsearch via a repository or ElasticsearchOperations, Spring Data uses its mapping converter.

Do not use ObjectMapper to serialize an entity and send the JSON string to Elasticsearch while assuming all @Field, @Id, or custom conversions metadata will automatically apply. If you choose low-level JSON manipulation, the application takes full responsibility for mapping and metadata.

## 14. Controlling Conversion Errors

The conversion process can fail on either side:

**When writing:**

- A Java value has no suitable converter.
- A custom converter throws an exception.
- Converted data does not match the Elasticsearch mapping.
- A date field has an invalid string or time unit.
- A nested object has an invalid structure.

**When reading:**

- An old document lacks a field required by the new entity.
- A field value cannot be converted to the target Java type.
- A custom reading converter cannot handle legacy data.
- A type hint no longer matches the current class.
- Mapping or field names changed without compatible entity updates.

When designing entities, consider backward compatibility. An index may contain documents written by multiple application versions. New entities must be able to read old data, or there must be a migration to standardize data prior to deployment.

Do not assume every field is always present. If data evolves over time, identify which fields are required and which can be null or have defaults in constructors and services.

## 15. Bidirectional Testing of Mapping

Mapping needs to be tested for both write and read paths. Merely checking that save does not throw an exception is not enough to guarantee the document has the expected structure.

Some aspects to verify:

1. The entity is written to the correct index.
2. @Id maps to the correct document ID.
3. Field names match the mapping, including renamed fields.
4. Numeric, boolean, date, and collection types have expected values.
5. Nested objects and nested fields have the right structure.
6. Custom converters write the right format and reading converters restore the right type.
7. The read-back entity retains important values.
8. SearchHit still provides the required ID, score, and metadata.
9. Old documents or missing fields are handled according to compatibility rules.

Conceptual integration test example:

~~~java
Product saved = productRepository.save(product);

Optional<Product> loaded =
        productRepository.findById(saved.getId());

assertThat(loaded).isPresent();
assertThat(loaded.get().getName()).isEqualTo(product.getName());
assertThat(loaded.get().getCategory()).isEqualTo(product.getCategory());
~~~

To inspect the actual _source structure and mapping, you can use the Elasticsearch client or REST API in tests. This helps catch cases where an entity reconstructs properly yet the index mapping does not match the intended queries.

## 16. Comprehensive Example: Bidirectional Product Conversion

Entity:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(name = "product_name", type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(type = FieldType.Keyword)
    private List<String> tags;

    // constructors, getters and setters
}
~~~

Save object:

~~~java
Product product = new Product(
        "product-100",
        "Mechanical Keyboard",
        "peripherals",
        new BigDecimal("89.90"),
        List.of("keyboard", "office")
);

productRepository.save(product);
~~~

Expected source section:

~~~json
{
  "product_name": "Mechanical Keyboard",
  "category": "peripherals",
  "price": 89.90,
  "tags": ["keyboard", "office"]
}
~~~

Read back:

~~~java
Product loaded = productRepository.findById("product-100")
        .orElseThrow();

System.out.println(loaded.getId());
System.out.println(loaded.getName());
System.out.println(loaded.getPrice());
~~~

The converter uses the field name product_name to assign back to the Java property name. The ID is restored from document metadata. Values for category, price, and tags are converted to their respective types according to metadata.

Combined flow:

~~~text
Product Java object
       |
       | repository.save()
       v
MappingElasticsearchConverter
       |
       | @Id, @Field, nested values,
       | custom conversions
       v
Spring Data Document
       |
       v
Elasticsearch _source + metadata

Elasticsearch hit
       |
       v
Spring Data Document + hit metadata
       |
       v
MappingElasticsearchConverter
       |
       | target type Product
       | convert fields and nested values
       | restore ID
       v
Product Java object
~~~

## 17. Conclusion

The workflow for converting Java objects to Elasticsearch Documents and reading them back is orchestrated by MappingElasticsearchConverter along with metadata from ElasticsearchMappingContext. Metadata defines the entity, ID, field names, field types, and object structures; custom conversions extend conversion behavior for domain-specific types.

When writing, Spring Data reads metadata, converts each property, and creates a Document for operations to send to Elasticsearch. When reading, the framework receives the source along with hit metadata, converts fields into Java types, and constructs the target object. Elasticsearch mapping continues to govern how data is indexed and queried.

Design entities and mappings as a bidirectional data contract. Verify both the written document structure and the restored objects, maintain backward-compatibility rules for legacy data, and add custom converters only when there is a clear conversion need.
