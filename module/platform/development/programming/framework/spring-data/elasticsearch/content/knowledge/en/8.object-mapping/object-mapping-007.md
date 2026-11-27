# Converting Nested Objects and Collections

In a Java application, an entity frequently contains child objects and collections: a customer has an address, an order has a list of line items, and a product has multiple tags or variants. When using Spring Data Elasticsearch, these properties are converted into objects and arrays in the JSON document. When reading the document, the converter reconstructs the Java objects based on the entity's declared types and mapping metadata.

To design this properly, distinguish two concerns: **how Spring Data converts Java structures into JSON** and **how Elasticsearch indexes that JSON structure**. A list of objects can be stored as an `object` array or a `nested` array; this choice affects how queries preserve relationships among fields within the same element, without changing how the converter builds the Java collection itself.

## 1. From Java Objects to JSON Documents

Spring Data Elasticsearch uses mapping metadata and `MappingElasticsearchConverter` to read and write entities. The converter inspects property types, annotations, and conversion rules to produce the corresponding JSON.

Example of an order containing recipient details and line items:

~~~java
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;

@Document(indexName = "orders")
public class Order {

    @Id
    private String id;

    private Customer customer;

    private List<OrderLine> lines;

    // Constructor, getters and setters
}

public class Customer {
    private String name;
    private Address address;

    // Constructor, getters and setters
}

public class Address {
    private String street;
    private String city;
    private String postalCode;

    // Constructor, getters and setters
}

public class OrderLine {
    private String productCode;
    private Integer quantity;
    private Long unitPriceInCents;

    // Constructor, getters and setters
}
~~~

When writing a populated entity, `_source` has the corresponding JSON structure:

~~~json
{
  "customer": {
    "name": "An Nguyen",
    "address": {
      "street": "12 Example Street",
      "city": "Ho Chi Minh City",
      "postalCode": "700000"
    }
  },
  "lines": [
    {
      "productCode": "KB-001",
      "quantity": 1,
      "unitPriceInCents": 129900
    },
    {
      "productCode": "MS-002",
      "quantity": 2,
      "unitPriceInCents": 45000
    }
  ]
}
~~~

The `Customer` object becomes a JSON object; `Address` becomes a nested object inside it; `List<OrderLine>` becomes a JSON array of objects. The converter does not require each child class to be a separate Elasticsearch document. Here, they are value objects embedded inside the `Order` document.

## 2. Converting Nested Objects

### 2.1. Nested POJOs

For a property with a concrete class type, the converter knows the target type from the property declaration. For instance, `Order.customer` has type `Customer`, and `Customer.address` has type `Address`. When reading `_source`, the converter has enough metadata to reconstruct each object.

Regular child classes do not need `@Document`. The `@Document` annotation is typically placed on the aggregate root managed by the repository, such as `Order`. Appearing inside a document does not turn a child class into an independent document.

You can explicitly declare field mappings with `@Field` when you want to control Elasticsearch types:

~~~java
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

public class Customer {

    @Field(type = FieldType.Keyword)
    private String name;

    @Field(type = FieldType.Object)
    private Address address;

    // Constructor, getters and setters
}
~~~

`FieldType.Object` describes how Elasticsearch indexes the child object. The converter still uses the Java type `Address` to transform the data.

### 2.2. Multi-level objects

Objects can be nested multiple levels deep. For example, `Order.customer.address` is stored under the path `customer.address.city`. Elasticsearch can query child fields using the full dot-separated path:

~~~json
{
  "query": {
    "term": {
      "customer.address.city": "Ho Chi Minh City"
    }
  }
}
~~~

With `object` mapping, sub-fields are indexed by path. There is no need to create separate indices for each child Java class. However, consider depth and total field count to avoid overly complex document structures or excessive dynamic field generation.

### 2.3. Maps and flexible structures

A `Map<String, Object>` property can be used when sub-field names or data structures vary across document types:

~~~java
import java.util.Map;

public class ProductMetadata {
    private Map<String, Object> attributes;

    // Getter and setter
}
~~~

JSON example:

~~~json
{
  "attributes": {
    "color": "black",
    "weightGrams": 850,
    "wireless": true
  }
}
~~~

Maps allow flexible data representation, but the Java type `Object` provides no static schema for individual values. The converter and dynamic mapping must infer or convert types from actual runtime values. If a key is sometimes numeric and sometimes a string, the Elasticsearch mapping may conflict. For important fields, declare an explicit schema or normalize types before writing.

## 3. Converting Collections of Simple Types

Collections such as `List<String>`, `Set<String>`, or `List<Long>` can be converted into JSON arrays. Elasticsearch does not have a dedicated mapping type named `array`; the mapping describes the type of each element.

Entity example:

~~~java
import java.util.List;
import java.util.Set;

public class Product {

    @Field(type = FieldType.Keyword)
    private List<String> tags;

    @Field(type = FieldType.Long)
    private Set<Long> compatibleModelIds;

    // Constructor, getters and setters
}
~~~

The document may contain:

~~~json
{
  "tags": ["keyboard", "wireless", "office"],
  "compatibleModelIds": [101, 205, 310]
}
~~~

The `tags` field still has a `keyword` mapping, and `compatibleModelIds` has a `long` mapping. Any field can accept either a single value or multiple values of the same type; Elasticsearch handles them as values of that field.

### 3.1. List, Set, and element ordering

`List` preserves element ordering in Java objects. The JSON array is written into `_source` in that order, so when read back through the converter, a List collection can be reconstructed in the stored order.

`Set` expresses uniqueness semantics on the Java side. During conversion, elements read into a Set follow the element class's `equals`/`hashCode` rules. Elasticsearch does not automatically enforce uniqueness on array values.

For querying, do not assume Elasticsearch preserves positional indices of a scalar array for index-based searching. Ordering in `_source` serves data reconstruction; the inverted index serves value-based searching. If ordering is part of business semantics, retain the data in `_source` and design queries/sorts appropriately rather than relying on array positions in the inverted index.

## 4. Collections of Objects: `object` or `nested`?

This is an important decision when a document contains a list of objects. Spring Data converts `List<OrderLine>` into a JSON array in both cases. The mapping annotation determines whether Elasticsearch treats that array as `object` or `nested`.

### 4.1. Default object arrays

Suppose a document has two order lines:

~~~json
{
  "lines": [
    { "productCode": "KB-001", "quantity": 1 },
    { "productCode": "MS-002", "quantity": 5 }
  ]
}
~~~

With the default `object` mapping, Elasticsearch flattens sub-field values during indexing. Conceptually, the indexed data behaves like bags of values:

~~~text
lines.productCode = ["KB-001", "MS-002"]
lines.quantity    = [1, 5]
~~~

When querying simultaneously for `productCode = KB-001` and `quantity = 5`, Elasticsearch can match two values from two different objects and return the document. This is undesirable if both conditions must match on the same order line.

### 4.2. Using `nested` to preserve per-element relationships

If you need to query multiple fields on the same object inside an array, declare the field as `nested`:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

public class Order {

    @Field(type = FieldType.Nested)
    private List<OrderLine> lines;

    // Other properties, getters and setters
}
~~~

With `nested` mapping, Elasticsearch indexes each array element as a separate internal document and preserves the relationship among fields within that element. A nested query requires conditions to match on the same element:

~~~json
{
  "query": {
    "nested": {
      "path": "lines",
      "query": {
        "bool": {
          "must": [
            { "term": { "lines.productCode": "KB-001" } },
            { "range": { "lines.quantity": { "gte": 5 } } }
          ]
        }
      }
    }
  }
}
~~~

The query above does not match the initial example because the line item with `productCode = KB-001` has `quantity = 1`, while the line item with `quantity = 5` is product `MS-002`.

Nested incurs higher storage and query overhead than regular objects. Only use it when you must preserve relationships among fields within the same array element. If you only filter on individual values independently or just read the JSON back, `object` is simpler.

## 5. Declaring Mappings for Nested Collections

For the `Order` and `OrderLine` entities, you can declare explicit mappings:

~~~java
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "orders")
public class Order {

    @Id
    private String id;

    @Field(type = FieldType.Object)
    private Customer customer;

    @Field(type = FieldType.Nested)
    private List<OrderLine> lines;

    // Constructor, getters and setters
}

public class Customer {
    private String name;
    private Address address;

    // Constructor, getters and setters
}

public class Address {
    private String street;
    private String city;

    // Constructor, getters and setters
}

public class OrderLine {
    @Field(type = FieldType.Keyword)
    private String productCode;

    @Field(type = FieldType.Integer)
    private Integer quantity;

    @Field(type = FieldType.Long)
    private Long unitPriceInCents;

    // Constructor, getters and setters
}
~~~

Conceptually, the corresponding Elasticsearch mapping is:

~~~json
{
  "mappings": {
    "properties": {
      "customer": {
        "properties": {
          "name": { "type": "text" },
          "address": {
            "properties": {
              "street": { "type": "text" },
              "city": { "type": "keyword" }
            }
          }
        }
      },
      "lines": {
        "type": "nested",
        "properties": {
          "productCode": { "type": "keyword" },
          "quantity": { "type": "integer" },
          "unitPriceInCents": { "type": "long" }
        }
      }
    }
  }
}
~~~

The converter uses Java types to serialize and reconstruct objects. Elasticsearch mapping determines how those fields are indexed. Both sides must align on field names and types, though `Nested` is not a separate Java collection conversion mechanism.

## 6. Reading and Writing via Repositories

Repositories can save and retrieve the entire aggregate root. The converter automatically handles nested objects and collections according to mapping metadata:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface OrderRepository extends ElasticsearchRepository<Order, String> {
}
~~~

Writing an order:

~~~java
Order order = new Order();
order.setId("ORD-1001");
order.setCustomer(new Customer(
        "An Nguyen",
        new Address("12 Example Street", "Ho Chi Minh City")));
order.setLines(List.of(
        new OrderLine("KB-001", 1, 129900L),
        new OrderLine("MS-002", 2, 45000L)));

orderRepository.save(order);
~~~

Reading it back:

~~~java
Order loaded = orderRepository.findById("ORD-1001")
        .orElseThrow();

Customer customer = loaded.getCustomer();
List<OrderLine> lines = loaded.getLines();
~~~

`save` writes the aggregate root as a single document in the `orders` index. `findById` retrieves the document by `_id` and the converter reconstructs `Customer`, `Address`, and the `OrderLine` list. There is no need to call separate repositories for child objects because they are not independent documents.

When searching by nested fields, you can use an appropriate repository query method if it can express a nested query, or use `ElasticsearchOperations`/native queries to explicitly specify the nested path and criteria. Any query against a nested field must be wrapped in an Elasticsearch nested query; dot notation alone does not trigger nested semantics.

## 7. Converting via `ElasticsearchOperations`

`ElasticsearchOperations` provides a high-level API for saving, reading, and searching entities. Object and collection conversion still relies on the mapping converter configured in the Spring context.

Example saving and reading an entity:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;

public class OrderService {

    private final ElasticsearchOperations operations;

    public OrderService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public Order save(Order order) {
        return operations.save(order);
    }

    public Order find(String id) {
        return operations.get(id, Order.class);
    }
}
~~~

When using query APIs, search hits can be mapped back to entities or read from source via projections. If source filtering excludes fields required to construct a child object, the resulting Java object will miss data or the converter may be unable to restore concrete types.

## 8. Empty Collections, Nulls, and Missing Fields

These states carry different meanings in JSON:

~~~json
{
  "lines": [
    { "productCode": "KB-001", "quantity": 1 }
  ],
  "tags": [],
  "comment": null
}
~~~

- `lines` has elements: a populated collection.
- `tags` is an empty array: the field exists in source with zero elements.
- `comment` is `null`: the field has a null value in source.
- Field omitted completely: the document does not contain that property.

By default, Elasticsearch does not index `null` values as searchable terms; `null_value` can be used on certain mapping types if a placeholder value is needed for indexing. `_source` can still store the original null value.

When reading, assignment behavior depends on the entity's constructor, property accessors, and mapping converter configuration. For collections, decide explicitly whether the application treats missing/null fields as `null` or empty collections. If business logic expects a list to always be non-null, initialize an empty collection in constructors or factories and verify how the converter populates the object.

Do not assume `null`, an omitted field, and `[]` are equivalent. They can carry different semantics when updating documents, checking existence, or displaying data.

## 9. Generic Collections and Element Types

Declaring concrete element types helps the converter know which objects to instantiate:

~~~java
private List<OrderLine> lines;
private Set<String> tags;
private Map<String, Address> offices;
~~~

With `List<OrderLine>`, the generic type supplies `OrderLine` metadata to convert each element. With `Map<String, Address>`, the converter can convert map values as `Address`.

Declaring raw collections or overly broad types drops type information:

~~~java
private List values;
private List<Object> attributes;
~~~

In that case, the converter lacks a concrete element type for building child classes. Elements may be read as simple types or `Map` structures depending on runtime values and mapping metadata; never assume the converter will automatically guess the right business class.

Prefer concrete generic types. If data is genuinely polymorphic, use an interface or abstract class with type hints or `@TypeAlias` and ensure implementations are registered with the mapping context. If the schema is intentionally dynamic, use `Map<String, Object>` deliberately and validate value types yourself.

Java generic type erasure also means type parameters are not retained in every runtime situation. Properties declared directly on entities generally provide generic metadata to Spring Data; custom generic wrappers or custom converters may need more explicit type declarations.

## 10. Custom Conversions for Special Objects

Common types like Strings, numbers, booleans, dates/times, collections, Maps, and POJOs are generally supported out of the box by the converter. If an object requires a special representation—such as a value object that should serialize to a string or custom JSON structure—you can register custom converters.

Example of a `Money` value object stored as an amount in cents:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class MoneyToLongConverter implements Converter<Money, Long> {

    @Override
    public Long convert(Money source) {
        return source.amountInCents();
    }
}
~~~

Reading converter for the reverse direction:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class LongToMoneyConverter implements Converter<Long, Money> {

    @Override
    public Money convert(Long source) {
        return Money.ofCents(source);
    }
}
~~~

Register both converters in `ElasticsearchCustomConversions` following the configuration mechanism for your Spring Data Elasticsearch version. Once registered properly, the mapping converter can invoke them when writing and reading `Money` properties.

Only write custom converters when default mapping fails to meet requirements. Converters must clearly specify reading vs. writing directions and avoid registering ambiguous pairs with identical source/target types. Also test against legacy data because changing JSON representations can make previously stored documents unreadable.

## 11. Partial Updates vs. Replacing Collections

When saving an entire entity, Spring Data converts the current object into a document according to the save mechanism. If a collection has changed, the written document reflects the collection state on the submitted object.

For instance, if an order previously had two line items and the new object has only one, replacing the document via an appropriate save operation updates `_source.lines` to match the new collection. Distinguish full document replacement from partial updates using `UpdateQuery` or equivalent APIs; partial updates can modify only specified fields while preserving other fields.

With nested arrays, if you need to add or remove an element, determine whether the update operation can be expressed accurately by the update API in use or whether you should read the aggregate, mutate the collection, and save the document back. Do not assume a repository save automatically diffs and syncs individual child items like a relational ORM.

Elasticsearch has no foreign key relationships or cascading behavior like JPA. Nested objects are stored within the same document; modifying the document modifies that JSON aggregate. If child objects need independent lifecycles, independent searches, or independent updates, consider modeling them as separate documents referenced by ID.

## 12. Common Pitfalls When Converting Objects and Collections

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Child object is not converted properly | Property declared with an overly broad type or JSON structure mismatches class. | Use concrete Java types, check field names and constructors/accessors. |
| Object collection reads fine, but queries cross-match fields across elements | Mapping is `object` while queries require conditions on the same element. | Switch mapping to `nested`, recreate/reindex, and use nested queries. |
| Inconsistent value types inside a Map | Dynamic mapping inferred a type from the first document and later saw another type. | Normalize data types or declare an explicit schema. |
| Collection returns null despite expecting an empty list | Field is missing/null or constructor does not initialize the collection. | Define null/empty semantics and initialize per domain requirements. |
| Generic list reads as Maps or simple types | Raw generic type or `Object` type parameter. | Declare concrete element types or configure polymorphic type conversion. |
| Custom converter is not invoked | Converter is unregistered or source/target types mismatch. | Verify `ElasticsearchCustomConversions` and converter direction. |
| Nested query returns no results | Query is missing `nested` wrapper or `path` is wrong. | Check mapping and `path` in the nested query. |

## 13. Design Workflow for Objects and Collections

When designing entities for Spring Data Elasticsearch, you can follow this order:

1. Decide what is the aggregate root stored as a document and which child classes are purely value objects.
2. Use concretely typed POJOs for nested objects; use generic collections with explicit element types.
3. Choose `object` for standard JSON structures; choose `nested` when queries must preserve field relationships within the same array element.
4. Pick mapping types for child fields based on search needs: `text`, `keyword`, numbers, dates/times, or booleans.
5. Decide domain semantics for List, Set, Map, null, and empty collections.
6. Use custom conversions only when a custom storage representation is needed, registering clear reading and writing converters.
7. Save sample documents, read them back via repositories/`ElasticsearchOperations`, and inspect runtime types and collection contents.
8. Test nested queries and source filtering if the application retrieves partial documents.

Spring Data Elasticsearch converts nested objects into JSON objects and collections into JSON arrays based on Java property types. Elasticsearch mappings determine how those fields are indexed: `object` suits standard objects, while `nested` preserves relationships among fields within each element during queries. Declaring clear element types, picking appropriate mappings, and defining collection semantics ensure data can be written, read, and searched consistently.
