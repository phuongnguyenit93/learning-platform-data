# Repeated Fields and Map Fields

## Learning Objectives

After this lesson, you will be able to:

- Choose **repeated** when an ordered list is needed and **map** when key-based lookup is needed.
- Declare repeated fields and map fields in proto3, understanding type constraints and default values.
- Use generated Java APIs such as **addXxx()**, **getXxxList()**, **putXxx()**, and **getXxxMap()**.
- Explain how both field kinds are encoded in binary Protobuf and represented in ProtoJSON.
- Design list/map updates through gRPC requests without confusing an empty collection with a request for no change.

## 1. Choose a List or a Key–Value Collection?

In **SPRING_GRPC** contracts, Protobuf messages describe RPC request/response data. When a message needs to hold multiple values, proto3 provides two common constructs:

- **repeated** represents a list of 0 or more elements. Both order and duplicate elements can carry meaning.
- **map** represents key–value pairs. Each key has only one value after parsing; iteration order is not part of the contract.

For example, a product might have multiple category tags and a set of attributes looked up by name:

~~~proto
syntax = "proto3";

message Product {
  string sku = 1;
  string name = 2;
  repeated string tags = 3;
  map<string, string> attributes = 4;
}
~~~

**tags** fits a list such as **["sale", "featured", "sale"]**: ordered and allowing duplicates. **attributes** fits data like **{"color":"blue","size":"M"}**: accessed by key and not relying on order.

| Requirement | Choose | Reason |
| --- | --- | --- |
| List of steps in execution order | **repeated** | Element order is preserved. |
| Multiple error codes, possibly duplicated | **repeated** | Lists preserve duplicate elements. |
| Attribute lookup by name | **map** | Each key maps to a single value. |
| Record list requiring sorting or pagination | **repeated** | Order is data that must be preserved. |
| Configuration set keyed by unique identifier | **map** | Convenient access by key. |

Do not choose map just because the current data looks like a JSON object. If order or duplicate keys carry meaning, use a repeated message to model it accurately.

## 2. Declaring a repeated Field

Place the **repeated** keyword before the data type:

~~~proto
message SearchResponse {
  repeated string suggestions = 1;
  repeated Product products = 2;
}

message Product {
  string sku = 1;
  string name = 2;
}
~~~

Repeated supports scalars, enums, and messages. A repeated field can hold:

- **0 elements**: an empty list, which is the default value.
- **1 element**: a single-element list.
- **Multiple elements**: preserves serialization/read order.
- **Duplicate elements**: allowed; Protobuf does not deduplicate automatically.

For instance, a skill list **["Java", "gRPC", "Java"]** keeps all three elements in exact order. If business logic needs deduplication, sorting, or normalization, the application must perform it.

Repeated fields lack dedicated **presence** like optional scalars. When no elements are present, the getter returns an empty list; the Java API does not generate **hasSuggestions()**. Therefore, looking at an empty list alone cannot distinguish a client omitting the field from sending an empty list intending to clear everything.

## 3. Declaring a map Field and Key Type Constraints

Map syntax:

~~~proto
message Product {
  string sku = 1;
  map<string, string> attributes = 2;
  map<string, int32> stock_by_warehouse = 3;
}
~~~

A map has one key type and one value type. Key types may only be:

- Protobuf-supported integer types, such as **int32**, **int64**, **uint32**, **sint32**, **fixed32**, **sfixed64**, and their corresponding integer variants.
- **bool**.
- **string**.

Do not use **float**, **double**, **bytes**, **enum**, or **message** as keys. Map values can be scalar, enum, or message; you cannot directly declare a nested map inside a map or a repeated field as the value type.

Example of a map whose value is a message:

~~~proto
message WarehouseStock {
  int32 available = 1;
  int32 reserved = 2;
}

message Inventory {
  map<string, WarehouseStock> stock_by_warehouse = 1;
}
~~~

Maps are suitable when keys are unique by the data model, such as warehouse codes, language codes, or attribute names. If you need multiple values for the same key, or need ordered pairs, use a **repeated message** containing key and value.

## 4. Generated Java API for repeated

Given:

~~~proto
message SearchResponse {
  repeated string suggestions = 1;
}
~~~

The Java message provides common read methods:

| Method | Meaning |
| --- | --- |
| **getSuggestionsList()** | Gets the list of elements. |
| **getSuggestionsCount()** | Gets the element count. |
| **getSuggestions(index)** | Gets the element at an index. |

The builder provides modification methods:

| Method | Meaning |
| --- | --- |
| **addSuggestions(value)** | Appends one element to the end. |
| **addAllSuggestions(values)** | Appends multiple elements to the end. |
| **setSuggestions(index, value)** | Replaces the element at an index. |
| **clearSuggestions()** | Removes all elements from the builder. |

Example:

~~~java
import com.example.catalog.v1.SearchResponse;
import java.util.List;

SearchResponse response = SearchResponse.newBuilder()
    .addSuggestions("Java")
    .addSuggestions("gRPC")
    .addAllSuggestions(List.of("Spring", "Protocol Buffers"))
    .build();

System.out.println(response.getSuggestionsCount()); // 4
System.out.println(response.getSuggestions(0));     // Java
System.out.println(response.getSuggestionsList());
~~~

Messages after **build()** are immutable. The list returned by a message is not meant for direct mutation; to modify it, use **toBuilder()** or create a new builder:

~~~java
SearchResponse revised = response.toBuilder()
    .setSuggestions(0, "Java 21")
    .addSuggestions("HTTP/2")
    .build();
~~~

For repeated messages, the builder also provides methods like **addProducts(product)**, **addAllProducts(...)**, and **getProductsBuilder(index)**. Each element remains an individual Protobuf message.

## 5. Generated Java API for map

Given:

~~~proto
message Product {
  map<string, string> attributes = 1;
}
~~~

The Java message normally provides:

- **getAttributesMap()**: gets the map.
- **getAttributesCount()**: number of key–value pairs.
- **getAttributesOrDefault(key, defaultValue)**: gets the value or returns an application-supplied default.
- **getAttributesOrThrow(key)**: gets the value and throws if the key does not exist.
- **containsAttributes(key)**: checks key existence.

The builder provides:

- **putAttributes(key, value)**: adds or replaces a key's value.
- **putAllAttributes(map)**: adds multiple pairs.
- **removeAttributes(key)**: removes a key.
- **clearAttributes()**: clears the entire map.

Example:

~~~java
import com.example.catalog.v1.Product;
import java.util.Map;

Product product = Product.newBuilder()
    .setSku("KB-42")
    .putAttributes("color", "black")
    .putAttributes("layout", "US")
    .putAllAttributes(Map.of("switch", "linear", "wireless", "true"))
    .build();

System.out.println(product.getAttributesCount());            // 4
System.out.println(product.getAttributesMap().get("color")); // black
System.out.println(product.containsAttributes("layout"));    // true

Product updated = product.toBuilder()
    .putAttributes("color", "white")
    .removeAttributes("wireless")
    .build();
~~~

**putAttributes("color", "white")** replaces the existing value for key color; it does not add a second color entry in the map. To store multiple values for one key, use a repeated message instead of a map.

## 6. How Protobuf Encodes repeated and map

### Repeated Scalars

In proto3, **packable** repeated scalars—such as integers, booleans, enums, and float/double—use **packed encoding** by default. Values are grouped into a single length-delimited payload under the same field.

Example:

~~~proto
message Quantities {
  repeated int32 values = 1;
}
~~~

For the list **[1, 2]**, a packed representation is:

~~~text
0A 02 01 02
|  |  |  |
|  |  +--+-- Two varint values: 1 and 2
|  +-------- Payload length: 2 bytes
+----------- Tag field 1, wire type 2 (length-delimited)
~~~

**string**, **bytes**, and **message** types are not packed; each element is encoded as a separate occurrence of the field. Protobuf parsers accept both packed and unpacked formats for repeated fields of packable types, ensuring compatibility across code-generation styles.

### Map Entries

A map is represented on the wire as a repeated field of synthetic entry messages. Conceptually, the declaration:

~~~proto
map<string, int32> stock = 1;
~~~

is wire-equivalent to entries with two fields:

~~~proto
message StockEntry {
  string key = 1;
  int32 value = 2;
}
~~~

Each entry is encoded as a length-delimited message at the outer map's field number. Field 1 inside the entry holds the key, and field 2 holds the value. This describes the encoding; in real schemas, do not manually declare this entry message instead of map syntax without a specific design reason.

Because maps use entry messages on the wire, binary data may contain multiple entries with the same key. When parsed into a map, duplicate keys follow the **last-value-wins** rule. Applications must not depend on entry ordering or use a map to represent change history over time.

## 7. Ordering, Duplicate Elements, and Duplicate Keys

The two constructs behave differently:

| Property | Repeated | Map |
| --- | --- | --- |
| Element order | Preserved | Not guaranteed |
| Duplicate elements/keys | Duplicates preserved | One effective value per key |
| Access | By index | By key |
| Default value | Empty list | Empty map |
| Java API | List and builder add | Map and builder put/remove |

Example:

~~~proto
message Example {
  repeated string codes = 1;
  map<string, string> labels = 2;
}
~~~

With **codes = ["A", "B", "A"]**, the count is 3 and the A-B-A order is preserved. With **labels = {"region":"north"}**, there is no concept of element position. If incoming map data has multiple entries with key region, the last value is retained after parsing.

A Java map is a lookup structure; do not rely on iteration order to determine display, processing, or event emission order. If stable ordering is needed, sort keys at the application layer or use a repeated message.

## 8. ProtoJSON: repeated Becomes Array, map Becomes Object

ProtoJSON represents:

- **repeated** as a JSON array.
- **map** as a JSON object; map keys become JSON property names (strings), even when keys in .proto are integers or bool.

Given:

~~~proto
message Product {
  repeated string tags = 1;
  map<string, string> attributes = 2;
}
~~~

A JSON representation:

~~~json
{
  "tags": ["sale", "featured"],
  "attributes": {
    "color": "black",
    "layout": "US"
  }
}
~~~

Lists preserve element order. JSON objects carry no ordering guarantee for map entries. For maps with numeric keys, such as **map<int32, string> names = 1**, JSON keys are still written as strings like **"10"**; the ProtoJSON parser converts keys back to the corresponding numeric type.

Empty repeated/map fields normally do not appear in JSON under the default printer, yet still evaluate to empty when reading the message. Do not use the presence or absence of a JSON property to infer that repeated/map has explicit presence like an optional scalar.

When official ProtoJSON is needed in Java, use **JsonFormat** from a runtime-compatible **protobuf-java-util**:

~~~java
import com.google.protobuf.util.JsonFormat;

String json = JsonFormat.printer().print(product);

Product.Builder parsed = Product.newBuilder();
JsonFormat.parser().merge(json, parsed);
Product restored = parsed.build();

System.out.println(restored.getTagsList());
System.out.println(restored.getAttributesMap());
~~~

Do not conflate ProtoJSON with JSON automatically generated by a general-purpose library serializing Java objects. Rules for field names, enums, 64-bit integers, bytes, and well-known types can differ.

## 9. Merge Semantics: repeated Appends, map Merges by Key

When using **mergeFrom()**, repeated fields typically **append elements** from the source message to the destination message. Maps are merged by key: new keys are added, and existing keys receive the value from the source message.

~~~java
Product current = Product.newBuilder()
    .addTags("sale")
    .putAttributes("color", "black")
    .putAttributes("layout", "US")
    .build();

Product incoming = Product.newBuilder()
    .addTags("featured")
    .putAttributes("color", "white")
    .putAttributes("material", "aluminum")
    .build();

Product merged = current.toBuilder()
    .mergeFrom(incoming)
    .build();

System.out.println(merged.getTagsList());
// [sale, featured]

System.out.println(merged.getAttributesMap());
// Contains color=white, layout=US, material=aluminum.
~~~

This has important implications when designing update APIs:

- To **add** tags, append/merge may fit.
- To **replace the entire** tag list, clear first or apply explicit replace rules.
- To **delete a key** from a map, merging a map without that key does not remove the old entry.
- To clear a map, invoke explicit clear operations in builder/domain logic.

Do not assume message merging equals a business PATCH. Protobuf defines structural merging; the application defines data-update operations.

## 10. Updating repeated/map via gRPC Requests

Repeated and map have no **hasXxx()** for the collection. A request containing an empty list can have the same observable state as a request that sends no elements. If the server must distinguish **no change** from **replace everything with empty**, add update semantics to the contract.

### Approach 1: FieldMask and Replacement Rules

~~~proto
syntax = "proto3";

import "google/protobuf/field_mask.proto";

message ProductSettings {
  repeated string tags = 1;
  map<string, string> attributes = 2;
}

message UpdateProductSettingsRequest {
  string product_id = 1;
  ProductSettings settings = 2;
  google.protobuf.FieldMask update_mask = 3;
}
~~~

The client puts the **tags** path into **update_mask** to signal that the server should process the tags field. If **settings.tags** is empty and the mask contains tags, the application can define this as **replacing the current list with an empty list**. If the mask does not contain tags, the server keeps the current list.

FieldMask only specifies **which fields are within the update scope**. The server must still define replace vs. merge behavior for repeated/map, validate paths, and handle absent or empty masks.

### Approach 2: Command Message with oneof

If the API must clearly distinguish replace, append, and clear, each operation can be explicitly modeled:

~~~proto
syntax = "proto3";

import "google/protobuf/empty.proto";

message StringList {
  repeated string values = 1;
}

message TagsMutation {
  oneof operation {
    StringList replace = 1;
    StringList append = 2;
    google.protobuf.Empty clear = 3;
  }
}

message UpdateTagsRequest {
  string product_id = 1;
  TagsMutation tags = 2;
}
~~~

Meaning:

- No operation branch selected: no tag operation requested.
- Select replace with empty values: replace the list with an empty list.
- Select append: append elements to the end in order.
- Select clear: remove all tags.

Since **TagsMutation** is a message field, it has presence; the inner **oneof** identifies the chosen action. This is an explicit way to express multiple operations. For maps, a similar command message can be built for replace, upsert, remove keys, and clear.

Do not add **optional** directly to repeated/map; use wrapper messages, oneof, or FieldMask depending on the semantics to express.

## 11. Choosing repeated message Over map for Ordered Key–Value Pairs

A map is unsuitable if the system must store change history, preserve duplicate keys, or sort in a user-chosen order.

Example requiring an ordered list of headers:

~~~proto
message HeaderEntry {
  string name = 1;
  string value = 2;
}

message RequestMetadata {
  repeated HeaderEntry headers = 1;
}
~~~

Two entries can have the same name with different values, and entry order is preserved. A map cannot represent this because a map holds only one effective value per key.

Conversely, if configuration has a single unique value per property name and order does not matter, **map<string, string>** is simpler and communicates the lookup intent directly.

Decisions should be driven by **data semantics**, not merely which syntax is shorter in the .proto file.

## 12. Schema Compatibility and Performance Considerations

When adding a repeated or map field to a released message, choose an unused number and keep existing fields intact. Old clients normally ignore the new field on the binary wire; the new server must handle empty collections when receiving requests from old clients.

When removing a used repeated/map field, reserve its old number and name to avoid reuse. Do not convert a repeated field into a map simply for lookup convenience: maps enforce unique keys and do not guarantee order, so legacy data with duplicates or meaningful ordering can lose semantics.

Some performance notes:

- Packable repeated scalars in proto3 use **packed encoding** by default, reducing repeated tags for numeric lists.
- Repeated messages/strings/bytes still incur tag and length overhead per element.
- Maps require an entry message per key–value pair; large maps have their own allocation and lookup overhead.
- Do not send a huge collection in a single message if size could exceed message limits, increase latency, or create memory pressure. Consider pagination or streaming RPCs.
- Do not try to save bytes by picking map/repeated against data semantics; misread data costs far more operationally than byte savings.

In streaming gRPC, a repeated field can batch a group of items in one message, whereas server-streaming can send items across multiple separate messages. The choice depends on size, desired latency, and the client's ability to process incrementally.

## 13. Common Mistakes

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| Using map when order is meaningful | Loses ordering guarantees across serialize/parse | Use a repeated message. |
| Using repeated when keys must be unique | Application must detect and resolve duplicates itself | Use map if order and duplicate keys are not needed. |
| Thinking repeated/map have **hasXxx()** | Code fails to compile or presence design is wrong | Check content/count; use wrapper/FieldMask to distinguish operations. |
| Assuming merging repeated replaces the list | Old and new lists get concatenated | Clear first then add, or apply replace semantics. |
| Assuming merging map deletes keys missing from source | Old keys remain present | Remove keys explicitly or replace the entire map. |
| Using map for duplicate keys | One value overwrites another | Use a repeated entry message. |
| Relying on map iteration order | Unstable results | Sort keys at the application layer if stable presentation is needed. |
| Declaring an invalid map key type | protoc rejects the schema | Choose an integer type, bool, or string. |
| Treating an empty collection as a delete command | May delete data unintentionally or skip the action | Use FieldMask or a oneof command message. |

## 14. Practice Exercise

An inventory management service needs to store product locations and product attributes:

~~~proto
message WarehouseItem {
  string sku = 1;
  repeated string warehouse_codes = 2;
  map<string, int32> quantity_by_warehouse = 3;
}
~~~

Complete the following:

1. Create a message with **warehouse_codes = ["HN", "HCM", "HN"]**; inspect element count, order, and duplicate elements.
2. Create a map with **HN = 10**, **HCM = 5**; update **HN = 12** and confirm the map still holds only one value for key HN.
3. Serialize/parse the message and check the list and map after the round-trip.
4. Use JsonFormat to observe repeated as an array and map as an object.
5. Call **mergeFrom()** with a message containing an additional warehouse code and an updated map entry for HN; explain why the list appends while the map replaces values by key.
6. Design an update request distinguishing **do not change warehouse_codes**, **replace the list with empty**, and **append a warehouse code**.
7. Explain why **map<string, int32>** cannot store two independent values for the same HN key and when it should be replaced with a repeated message.

**Completion criteria:** choose the right structure based on ordering/keys, use Java builders properly, predict merge semantics, and design clear collection update commands.

## 15. Key Takeaways

- **repeated** is an ordered list allowing duplicate elements; **map** is a key–value collection with no ordering guarantee and one effective value per key.
- Repeated/map default to empty and **do not have explicit presence** for the collection as a whole.
- Java uses **add/addAll/getList** for repeated and **put/putAll/remove/getMap** for map.
- ProtoJSON represents repeated as an **array** and map as an **object**; never rely on object ordering.
- **mergeFrom()** normally appends repeated fields and merges maps by key; it does not implicitly perform business replace/clear operations.
- When you must distinguish no change from replacing a collection with empty, use **FieldMask**, wrapper messages, or a **oneof** expressing the action.

Choosing correctly between repeated and map ensures Protocol Buffers contracts accurately reflect data structures, preserve ordering when needed, avoid key loss, and help Spring gRPC applications handle collections effectively across both unary and streaming RPCs.
