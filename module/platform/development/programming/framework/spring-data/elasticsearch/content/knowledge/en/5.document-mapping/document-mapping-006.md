# MappingElasticsearchConverter and Mapping Metadata

Spring Data Elasticsearch lets applications work with Elasticsearch documents using Java classes. When saving an object, the application needs to convert Java properties into an appropriate document structure; when reading results, the application needs to convert the document back into an object. `MappingElasticsearchConverter` handles this bidirectional conversion based on mapping metadata collected by Spring Data from classes, fields, data types, and annotations.

To understand the converter, distinguish three components: the **Java entity** is the data model in the application; **mapping metadata** describes how the entity and its properties correspond to a document; and **Elasticsearch index mapping** is the field structure stored on the cluster. These three components are related but are not the same thing. The converter uses application metadata to transform data; the cluster uses index mapping to analyze, index, and query data.

## 1. Position of MappingElasticsearchConverter in the Data Flow

### 1.1. Bidirectional Conversion

Suppose an application has a `ProductDocument` class and wants to save a product into the `products` index. A service typically calls a repository or `ElasticsearchOperations`. Spring Data uses the converter to turn the object into a document before sending a request to Elasticsearch.

When searching, Elasticsearch returns document data. Spring Data converts that document into a Java object before returning the result to the service.

~~~mermaid
flowchart TD
    A[ProductDocument object] --> B[MappingElasticsearchConverter]
    B --> C[Document representation]
    C --> D[Elasticsearch Java client]
    D --> E[Elasticsearch index]
    E --> D
    D --> F[Document response]
    F --> G[MappingElasticsearchConverter]
    G --> H[ProductDocument object]
~~~

The two directions can be summarized as:

| Direction | Input | Output | Purpose |
|---|---|---|---|
| Write | Java Object | Document | Prepare data for indexing or updating |
| Read | Document | Java Object | Map search results back to application types |

The converter lets services work with strongly typed objects instead of manually building JSON for every operation. Repository operations and `ElasticsearchOperations` can share this same mapping mechanism.

### 1.2. The Converter Is Not an HTTP Client

Responsibilities must be distinguished:

- `MappingElasticsearchConverter` converts between Java objects and Spring Data's document representation.
- `ElasticsearchOperations` provides high-level operation APIs such as save, search, delete, and query execution.
- Repositories provide an interface-based data access abstraction.
- The Elasticsearch Java client sends HTTP requests to the cluster and receives responses.
- Elasticsearch index mapping governs how the cluster interprets and indexes fields.

The converter does not open network connections, authenticate accounts, or send HTTP requests. Those responsibilities belong to the client and connection configuration. Nor does the converter execute search business logic or decide which documents should be saved.

### 1.3. The Converter Is Managed by Spring

In a Spring Boot application using standard Spring Data Elasticsearch configuration, mapping components are configured and managed in the application context. Repositories and `ElasticsearchOperations` use the corresponding converter.

You typically do not need to instantiate `MappingElasticsearchConverter` yourself in a service. Declare entities and metadata properly; only customize conversions when an application's data types require a special representation.

## 2. What Is Mapping Metadata?

### 2.1. Metadata Describes Entities and Properties

Metadata is information describing an entity's structure and how each property is mapped. Spring Data collects metadata from:

- Java class types and property types.
- Class-level annotations such as `@Document`.
- Property-level annotations such as `@Id`, `@Field`, `@Transient`, and `@MultiField`.
- Constructor or factory method information used to instantiate objects.
- Default data type conversion rules and custom conversions.

Example:

~~~java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(name = "product_name", type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    public ProductDocument() {
    }

    // Constructors, getters, and setters omitted.
}
~~~

From the class above, Spring Data can recognize:

- `ProductDocument` is an entity stored in the `products` index.
- `id` is the document identifier.
- `name` is mapped to the `product_name` field of type `text`.
- `category` is a `keyword` field.
- `price` is mapped to the numeric type `double`.

Java property names do not have to match Elasticsearch field names. Metadata allows declaring the target field name with `@Field(name = "...")`.

### 2.2. Mapping Context

Spring Data uses a mapping context to manage information about entities and properties. In Spring Data Elasticsearch, `SimpleElasticsearchMappingContext` is an Elasticsearch-specific mapping context implementation.

The mapping context provides the metadata model that the converter can look up, such as:

- Which document type an entity class corresponds to.
- Which properties the entity has.
- Which property is the ID.
- What the field name in the document is.
- What the property's data type is.
- Which special mapping annotations the property has.
- How nested properties are described.

In Spring Data's model, entity and property metadata are typically represented through abstractions such as `ElasticsearchPersistentEntity` and `ElasticsearchPersistentProperty`.

You can visualize this as:

~~~text
ProductDocument.class
       |
       v
Mapping Context
       |
       +--> Entity metadata
       |      indexName = products
       |
       +--> Property metadata
              id       -> document id
              name     -> product_name / text
              category -> category / keyword
              price    -> price / double
       |
       v
MappingElasticsearchConverter
~~~

The mapping context is application-side metadata. It is not the mapping currently stored on the Elasticsearch cluster. The cluster may hold an older mapping or a manually created mapping; therefore, Java metadata and the actual mapping must be kept consistent.

### 2.3. Metadata Is Built and Reused

Mapping metadata is built by Spring Data from the entity types the application uses. The converter looks up this metadata when reading or writing documents. Because of this, the converter does not need to re-parse all class annotations on every save.

If you change property names, Java types, or annotations, the application's metadata reflects the changes after the application restarts with the new code. However, the existing index mapping on the cluster does not automatically change just because the Java class changed.

## 3. Entity-Level Annotations

### 3.1. `@Document`

`@Document` marks a class as an entity mapped to an Elasticsearch document. The most common attribute is `indexName`.

~~~java
@Document(indexName = "products")
public class ProductDocument {
    // Document properties.
}
~~~

`indexName` indicates the index the entity is bound to. Repository or operations calls based on the entity can use this metadata to determine the target index.

Other `@Document` attributes can control behaviors related to index creation and type hints, depending on the Spring Data Elasticsearch version. Consult the documentation of the exact version you are using when modifying those options.

`@Document` does not mean a Java class creates an Elasticsearch cluster on its own. It provides metadata so Spring Data knows which index the entity belongs to and applies the corresponding mapping.

### 3.2. One Class Usually Represents One Document Type

Suppose the application has two types of data:

~~~java
@Document(indexName = "products")
public class ProductDocument {
    @Id
    private String id;

    private String name;
}

@Document(indexName = "categories")
public class CategoryDocument {
    @Id
    private String id;

    private String name;
}
~~~

The two classes have different index metadata. Each entity's repository operates on the corresponding document type.

The chosen index name should be stable and match the deployment strategy. If data needs to be separated by environment, configure index names using a strategy the application supports; avoid letting services concatenate index names arbitrarily across multiple places.

## 4. Property-Level Annotations

### 4.1. `@Id`

`@Id` marks a property as the document identifier:

~~~java
@Id
private String id;
~~~

Elasticsearch stores the document identifier in `_id` metadata. Spring Data uses the marked property to read or write the ID during document operations.

The ID is not like a regular searchable field. If you need to search by a business code such as `productCode`, declare a separate property and map the field appropriately; do not assume every business code belongs in `_id`.

### 4.2. `@Field`

`@Field` supplies metadata for a property. Important details may include field name, Elasticsearch data type, analyzer, search analyzer, date/time format, indexing or storage capabilities, and other mapping options.

Example:

~~~java
@Field(name = "product_name", type = FieldType.Text, analyzer = "standard")
private String name;

@Field(type = FieldType.Keyword)
private String category;

@Field(type = FieldType.Boolean)
private boolean available;

@Field(type = FieldType.Long)
private Long stockQuantity;
~~~

Common types:

| FieldType | Purpose |
|---|---|
| `Text` | Text analyzed for full-text search |
| `Keyword` | Strings used for exact matching, filtering, grouping, or sorting |
| `Integer`, `Long` | Integers |
| `Float`, `Double`, `Half_Float`, `Scaled_Float` | Floating-point numbers according to the chosen mapping type |
| `Boolean` | True/false values |
| `Date` | Dates or timestamps |
| `Object` | Nested JSON objects |
| `Nested` | Arrays of objects where field relationships within each element must be preserved during queries |
| `Binary` | Binary data as supported by Elasticsearch |

Do not pick a `FieldType` just because its name resembles the Java type. Choose based on how the data is queried. For example, a status string usually suits `Keyword`, whereas a long description usually suits `Text`.

### 4.3. Renaming Fields in Documents

When the field name in Elasticsearch differs from the Java property name, use `name`:

~~~java
@Field(name = "created_at", type = FieldType.Date)
private Instant createdAt;
~~~

The application still uses the Java name `createdAt`, while the document uses the field `created_at`. The converter relies on metadata to map between the two names accurately.

Renaming a field in the class does not automatically rename old fields on the cluster. If the existing index has a `createdAt` field while new code uses `created_at`, you need a plan to migrate data or create a new index and reindex if old data must be retained.

### 4.4. `@Transient`

A property used only for in-application calculations that should not be persisted into the document can be annotated with `@Transient`:

~~~java
@Transient
private String displayLabel;
~~~

The converter ignores transient properties during regular mapping. When reading a document, this property is not restored from Elasticsearch and the application must compute or assign it if needed.

Do not use `@Transient` for business data that must be persisted and searched. If a property needs to be written or read in one direction only, check the read-only/write-only annotations supported by Spring Data Elasticsearch in the version in use.

## 5. Mapping Nested Objects and Collections

### 5.1. Nested Objects

A document can contain nested objects:

~~~java
public class BrandDocument {

    private String code;

    @Field(type = FieldType.Keyword)
    private String name;

    public BrandDocument() {
    }
}

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Object)
    private BrandDocument brand;
}
~~~

The document can have the structure:

~~~json
{
  "name": "Mechanical Keyboard",
  "brand": {
    "code": "B01",
    "name": "Example"
  }
}
~~~

The converter continues using the nested class's metadata to convert properties inside the object. Therefore, metadata applies not only to the root entity but is also important for referenced object types.

### 5.2. Lists of Objects

A collection property can also contain objects:

~~~java
public class ProductImage {

    @Field(type = FieldType.Keyword)
    private String url;

    @Field(type = FieldType.Integer)
    private Integer position;

    public ProductImage() {
    }
}

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Object)
    private List<ProductImage> images;
}
~~~

The converter maps each element in the collection according to the element type. When reading a document, it creates the collection and converts each nested object into a `ProductImage`.

The Java type `List<ProductImage>` describes the data structure in the application. The `Object` or `Nested` annotation describes how Elasticsearch interprets that structure during indexing and querying.

### 5.3. Distinguishing `Object` and `Nested`

This is an important point when designing mappings. Both `Object` and `Nested` can hold nested objects, but Elasticsearch handles arrays of objects differently between them.

Suppose an order has two lines:

~~~json
{
  "lines": [
    { "product": "Keyboard", "color": "Black" },
    { "product": "Mouse", "color": "White" }
  ]
}
~~~

With standard `object` mapping, Elasticsearch can flatten field values across the object array. A query combining `product = Keyboard` and `color = White` risks matching values coming from two different elements.

If you need to preserve relationships between fields of each element during queries, use `nested`:

~~~java
@Field(type = FieldType.Nested)
private List<OrderLine> lines;
~~~

`Nested` has its own storage and query cost because Elasticsearch handles each nested element as an independent internal document. Choose `nested` only when query requirements need to preserve field relationships within the same element. The converter can convert objects/collections; query semantics are still governed by index mapping and query type.

## 6. Multi-fields and Multiple Ways to Search One Property

### 6.1. Why Are Multi-fields Needed?

A string may need to be searched in multiple ways. For example, a product name needs full-text search while also needing exact matching or sorting on the entire string. An analyzed `text` field is usually unsuitable for all those needs.

Elasticsearch supports multi-fields: the same source value is indexed in multiple ways under subfields.

### 6.2. Declaring with `@MultiField`

Example declaring a product name with a `text` main field and a `keyword` subfield:

~~~java
@MultiField(
    mainField = @Field(type = FieldType.Text, analyzer = "standard"),
    otherFields = {
        @InnerField(suffix = "keyword", type = FieldType.Keyword)
    }
)
private String name;
~~~

The mapping can create two corresponding fields:

- `name`: used for full-text search.
- `name.keyword`: used for exact matching, aggregations, or sorting by keyword value.

The converter writes the property value into the source field; the Elasticsearch index mapping defines the indexed subfields. You do not need to declare two separate Java properties merely to store two ways of analyzing the same value.

Verify the subfield name and actual mapping created on the cluster before writing queries. Annotations in code are input metadata; an existing index might not be updated yet.

## 7. Data Type Conversion

### 7.1. Simple Types and Types Requiring Conversion

The converter supports common Java types such as strings, numbers, booleans, enums, dates/times, collections, maps, and nested objects according to Spring Data Elasticsearch mapping rules.

However, an application may have custom domain types without a suitable direct document representation. For example:

- `Money` consisting of currency and amount.
- `EmailAddress` needing lowercase normalization.
- `Coordinate` needing conversion into a structure agreed upon by the application.
- A value object needing storage as a string or JSON object per custom convention.

For such types, you can register custom converters to define how writing and reading work.

### 7.2. Custom Writing Converter and Reading Converter

Suppose the application has a value object:

~~~java
public record Money(String currency, BigDecimal amount) {
}
~~~

To store `Money` as a string such as `USD 19.95`, create a converter for the write direction:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class MoneyToStringConverter implements Converter<Money, String> {

    @Override
    public String convert(Money source) {
        return source.currency() + " " + source.amount().toPlainString();
    }
}
~~~

And a converter for the read direction:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class StringToMoneyConverter implements Converter<String, Money> {

    @Override
    public Money convert(String source) {
        String[] parts = source.split(" ", 2);

        if (parts.length != 2) {
            throw new IllegalArgumentException("Invalid money value: " + source);
        }

        return new Money(parts[0], new BigDecimal(parts[1]));
    }
}
~~~

`@WritingConverter` marks a converter used when writing data; `@ReadingConverter` marks a converter used when reading data. Specifying the direction helps Spring Data select the right conversion, especially when multiple converters relate to types convertible in multiple ways.

Production converters should validate input data and handle malformed values per application conventions. The example above illustrates a simple format; if data may contain spaces or multiple currency rules, use a more robust format.

### 7.3. Registering Custom Conversions

Converters must be registered with `ElasticsearchCustomConversions` so Spring Data uses them:

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

In Spring Boot configuration, the custom conversions bean is used to configure Spring Data Elasticsearch's conversion service. If a project creates a custom Elasticsearch configuration, ensure custom conversions are attached to the exact mapping converter used by `ElasticsearchOperations` and repositories.

Do not instantiate an isolated `MappingElasticsearchConverter` inside a service solely to invoke it manually. Doing so can cause the conversion rules of your standalone converter to diverge from the repository's converter.

### 7.4. Attaching a Custom Type to an Entity

After registering conversions, an entity can use `Money` as a property:

~~~java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String name;

    @Field(type = FieldType.Keyword)
    private Money price;
}
~~~

The example above assumes `Money` converts into a string like `USD 19.95`, so `Keyword` fits if the application needs to store and match that string representation. If filtering by amount or currency separately is required, representing it as an object with `amount` and `currency` fields is usually more appropriate; custom converters should be designed accordingly.

Choose the data representation according to how the application queries. Just because a value object can be converted to a string does not mean a string is always the best mapping.

## 8. Constructor Mapping and Object Instantiation When Reading

### 8.1. The Converter Must Be Able to Instantiate Java Objects

When reading a document, the converter needs to create an instance of the entity and populate its properties. For mutable classes, a no-arg constructor combined with setters or field access may be used depending on how mapping is configured.

For immutable objects, a constructor or factory method can accept property values to construct the instance:

~~~java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private final String id;

    private final String name;

    public ProductDocument(String id, String name) {
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

Spring Data needs to identify the right constructor and map parameters to properties. Parameter names must be retained in compiled metadata or explicitly specified via mechanisms supported by Spring Data.

### 8.2. `@PersistenceCreator`

If a class has multiple constructors and Spring Data cannot determine which constructor to use for creating the entity, `@PersistenceCreator` can be used to mark the appropriate constructor or factory method:

~~~java
@PersistenceCreator
public ProductDocument(String id, String name) {
    this.id = id;
    this.name = name;
}
~~~

This annotation makes entity instantiation clear when reading data. It does not replace property metadata; parameter types and names must still correspond to the data being mapped.

For Java records, components provide an immutable structure and a canonical constructor. Spring Data supports record mapping in compatible versions; you still need to check data types, field names, and custom conversions for each component.

## 9. Type Hints and Polymorphic Data Types

### 9.1. Why Is Type Information Needed?

A property may be declared using an interface or superclass while holding different concrete subtypes at runtime. When writing an object, the converter needs a way to record which concrete type was stored. When reading, type information helps instantiate the right subtype.

Spring Data Elasticsearch supports storing type hints in documents based on mapping configuration. Type hints are commonly represented via a metadata field such as `_class`; writing and reading behavior depends on type mapping configuration and library version.

Example of a property declared as an interface:

~~~java
public interface PaymentMethod {
}

public class CardPayment implements PaymentMethod {
    private String lastFourDigits;
}

public class BankTransfer implements PaymentMethod {
    private String bankCode;
}
~~~

If a document contains a `PaymentMethod`, the converter needs sufficient information to restore the exact concrete type on read. If type hints are disabled or removed, the application must have another rule to determine the subtype, such as a domain-managed discriminator field.

### 9.2. Controlling Type Hints

Do not rely on type hints without understanding their impact. Type hints add application type information to documents; this can be helpful for polymorphic mapping, but also couples stored data to class/package names.

If using type aliases or renaming packages/classes, review previously stored data. When class structures change, old documents may still carry old type information. Have a compatibility or data migration strategy when needed.

Disable type hints only when the application has an appropriate way to restore types. For concrete, non-polymorphic properties, reading is usually simpler because the target type is already known from entity metadata.

## 10. Application Metadata vs. Index Mapping on the Cluster

### 10.1. Two Related but Distinct Mappings

Keep them separate:

**Application-side mapping metadata** is the description Spring Data gathers from classes, properties, annotations, and conversion rules.

**Elasticsearch-side index mapping** is the actual configuration on the cluster, determining field types, analyzers, dynamic behavior, and how data is indexed.

The converter uses application-side metadata to convert objects and documents. Elasticsearch uses index mapping to process data. Both sides must align, but updating one does not automatically guarantee the other is updated.

### 10.2. Annotations Do Not Automatically Fix Old Mappings

Suppose the initial version declared:

~~~java
@Field(type = FieldType.Text)
private String category;
~~~

Later, the code changes to:

~~~java
@Field(type = FieldType.Keyword)
private String category;
~~~

The new code has `Keyword` metadata, but the existing index may still retain a `text` mapping. Elasticsearch does not allow arbitrarily changing the type of a field already created in an existing mapping this way.

Plan an index change—typically creating a new index with the desired mapping, reindexing the data, and then switching the alias or application configuration to the new index. The specific strategy depends on downtime requirements, data volume, and deployment setup.

### 10.3. Verifying the Actual Mapping

When queries return unexpected results, inspect the index mapping directly on Elasticsearch. Do not read Java annotations alone and assume the cluster has the identical configuration.

You can call the mapping API over HTTP:

~~~http
GET /products/_mapping
~~~

The response shows the field types and mapping options the cluster is using. Compare them with Java metadata to spot discrepancies in field names, field types, analyzers, date formats, or nested structures.

### 10.4. Dynamic Mapping

If an index permits dynamic mapping, Elasticsearch can infer field types automatically when encountering new fields. This is handy for initial experimentation, but can lead to unintended mappings if input data is inconsistent.

For example, the first document sends `price` as a number, while another document sends the same field as a string. The previously created mapping may cause the later document to be rejected or converted unexpectedly.

Declaring explicit metadata and designing mappings upfront generally keeps systems more stable. Dynamic mapping should be used intentionally, especially with evolving data structures.

## 11. Detailed Write and Read Flows

### 11.1. When Writing an Object

When the application calls `save()` or an equivalent write operation, the conceptual flow proceeds as follows:

1. The repository or `ElasticsearchOperations` receives the Java object.
2. Spring Data looks up entity metadata from the mapping context.
3. `MappingElasticsearchConverter` traverses the properties to write.
4. The converter determines field names and mapping rules from metadata.
5. Values are converted according to data types and registered custom conversions.
6. Nested objects, collections, and type information are processed according to their metadata.
7. The converter builds a document representation for the write operation.
8. The Elasticsearch client sends the request to the cluster.
9. Elasticsearch applies the index mapping to store and index the document.

### 11.2. When Reading a Document

When searching or reading by ID:

1. Elasticsearch returns the document in the response.
2. Spring Data receives the document representation from the client.
3. `MappingElasticsearchConverter` looks up target entity metadata.
4. The converter determines the appropriate constructor or instantiation mechanism.
5. Fields are read according to declared names and types.
6. Custom reading converters are applied where needed.
7. Nested objects, collections, and subtypes are restored per metadata.
8. Spring Data returns the Java object to the repository or operations caller.

If a property cannot be converted, reading may fail. In that case, inspect the actual data in the index, Java types, annotations, and relevant custom converters.

## 12. Common Mapping Issues

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Field in document has unexpected name | `@Field(name = "...")` or naming convention mismatch | Check metadata and actual `_source` |
| Type conversion error on read | Old data incompatible with current Java type | Inspect document, custom converter, and schema change history |
| Subtype cannot be restored | Missing or incompatible type information | Check type hint or domain discriminator |
| Query does not match even though object was saved | Index mapping/analyzer differs from Java metadata | Inspect mapping API and analyzer |
| Property does not appear in document | Property is transient or unmapped | Check `@Transient`, accessors, and metadata |
| Nested object queried incorrectly | Used `object` when requirements need `nested` | Redesign mapping and query appropriately |
| Changed `Text` to `Keyword` but query still behaves wrongly | Old index still holds old mapping | Create new mapping/index and reindex if needed |
| Custom converter is not applied | Converter not registered in active conversion configuration | Check `ElasticsearchCustomConversions` bean and client/operations config |
| Date/time value error | Inconsistent format or timezone | Check Java time type, date format, and indexed data |

When troubleshooting, trace data across layers: Java object, metadata, converter-produced document, sent request, and actual cluster mapping. This helps pinpoint whether the bug lies in conversion or in index/query configuration.

## 13. Comprehensive Practice

Suppose you need to map a product with an ID, name, category, price, and brand. An example entity:

~~~java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @MultiField(
        mainField = @Field(type = FieldType.Text, analyzer = "standard"),
        otherFields = {
            @InnerField(suffix = "keyword", type = FieldType.Keyword)
        }
    )
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(type = FieldType.Object)
    private BrandDocument brand;

    public ProductDocument() {
    }

    // Constructors, getters, and setters omitted.
}
~~~

When saving the object, the converter uses metadata to:

- Place `id` into the document identifier.
- Write `name` according to the main field and multi-field mapping.
- Write `category` as a keyword value.
- Convert `price` into a numeric value.
- Convert `brand` into a nested object according to `BrandDocument`'s metadata.

After saving, you can inspect the document and mapping on the cluster to confirm actual data aligns with the design.

You can extend this exercise yourself by adding a `createdAt` property of type `Instant`, an `images` collection, or a `Money` value object with custom converters. Each time you add a property, decide three things: what the Java representation is, how mapping metadata describes it, and how Elasticsearch queries need to operate on that field.

## 14. Key Takeaways When Working with the Converter

- `MappingElasticsearchConverter` converts Java objects and documents bidirectionally.
- The mapping context manages entity/property metadata for the converter to use.
- `@Document` describes the entity and index; `@Id` describes the identifier; `@Field` describes field mapping.
- `@Transient` excludes a property from regular mapping.
- Objects, collections, nested types, and multi-fields must be designed around query goals.
- Custom reading/writing converters handle domain types needing special representations.
- Constructor mapping and type hints affect object reconstruction.
- Java metadata does not mean the index mapping on the cluster has been updated.
- Changing an existing field's type usually requires creating a new index and reindexing.
- Repositories and `ElasticsearchOperations` should share Spring-managed converter configuration.

By understanding the converter and metadata, you can read mapping annotations, predict how Java data becomes a document, and diagnose why read/write results differ from expectations. This is the foundation for continuing to design mappings, queries, and complex document handling in Spring Data Elasticsearch.
