# Mapping Collections, Maps, and Property Paths in Spring Data Redis

When storing a Java entity in Redis via **Spring Data Redis Repositories**, an application usually does not need to manually convert each property into an `HSET` command. Spring Data Redis uses **object mapping** to convert an object and its nested properties into Redis data that can be saved and read back. With `List`, `Set`, `Map`, and nested objects, the key is understanding the **property path**: how a child field is represented as a field name in a Redis Hash.

This lesson focuses on entity mapping through `@RedisHash`, `@Id`, `RedisRepository`, and `MappingRedisConverter`, while distinguishing it from directly manipulating Redis List, Set, Hash, or JSON structures.

## 1. Entity Storage Model: One Redis Hash Key, Many Fields

Suppose an application has a product with code `p-100`, display name, list of variants, set of tags, and specifications. In Java, this is an **object graph**: the root entity contains simple properties, collections, and child objects. With standard Redis repository mapping, Spring Data Redis stores the root entity under a single key such as:

```text
products:p-100
```

The value at this key is a **Redis Hash**: each property is converted into one or more `field -> value` pairs.

```text
Redis key: products:p-100
Redis type: hash

name                              -> "Study Desk"
origin.city                       -> "Hanoi"
origin.country                    -> "VN"
variants.[0].sku                  -> "DESK-BLACK"
variants.[0].stock                -> "12"
variants.[1].sku                  -> "DESK-WHITE"
variants.[1].stock                -> "7"
specifications.[material]         -> "wood"
specifications.[widthCm]          -> "120"
tags.[0]                          -> "furniture"
tags.[1]                          -> "workspace"
```

This is a **typical field-path illustration**, not a guarantee of display order or exact byte representation for every serializer configuration. A Redis Hash does not guarantee field order in `HGETALL`; technical fields such as `_class`, `id`, or mapping metadata may appear depending on the model and configuration. For a `Set`, the illustrative index positions should not be treated as a stable order.

The core point: a Java `List` inside an entity **does not automatically become a Redis List**; a `Set<String>` inside an entity **does not automatically become a Redis Set**. They can be flattened into fields of **the same Redis Hash** managed by the repository mapping mechanism.

### 1.1. Three Levels of Paths

| Java Property Form | Example Path in Redis Hash | Meaning |
|---|---|---|
| Single value | `name` | Direct field on the entity |
| Nested object | `origin.city` | `city` property inside `origin` |
| Positional collection | `variants.[0].sku` | `sku` of the element at index `0` in `variants` |
| Keyed map | `specifications.[material]` | Value corresponding to key `"material"` |
| Map containing objects | `offices.[hanoi].city` | `city` in the object at map key `"hanoi"` |
| Collection of simple values | `photoUrls.[1]` | Element at index `1` in the list |

Dot-separated segments express the depth of the Java structure. Square brackets `[...]` represent a **collection element** or **map key**. Do not treat this string as special Redis query syntax: for an `HGET` command, the entire `variants.[0].sku` is simply **a single hash field name**.

## 2. Creating an Entity with `List`, `Set`, `Map`, and Nested Objects

The example below uses standard POJOs. Each class has a no-arg constructor and accessors so Spring Data can instantiate, read, and write data.

```java
package com.example.catalog;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("products")
public class Product {

    @Id
    private String id;

    private String name;

    private Origin origin;

    private List<Variant> variants = new ArrayList<>();

    private Map<String, String> specifications = new LinkedHashMap<>();

    private Set<String> tags = new LinkedHashSet<>();

    public Product() {
    }

    public Product(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public Origin getOrigin() { return origin; }
    public void setOrigin(Origin origin) { this.origin = origin; }

    public List<Variant> getVariants() { return variants; }
    public void setVariants(List<Variant> variants) { this.variants = variants; }

    public Map<String, String> getSpecifications() { return specifications; }
    public void setSpecifications(Map<String, String> specifications) {
        this.specifications = specifications;
    }

    public Set<String> getTags() { return tags; }
    public void setTags(Set<String> tags) { this.tags = tags; }
}
```

Nested object:

```java
package com.example.catalog;

public class Origin {

    private String city;
    private String country;

    public Origin() {
    }

    public Origin(String city, String country) {
        this.city = city;
        this.country = country;
    }

    public String getCity() { return city; }
    public void setCity(String city) { this.city = city; }

    public String getCountry() { return country; }
    public void setCountry(String country) { this.country = country; }
}
```

Element of `List<Variant>`:

```java
package com.example.catalog;

public class Variant {

    private String sku;
    private int stock;

    public Variant() {
    }

    public Variant(String sku, int stock) {
        this.sku = sku;
        this.stock = stock;
    }

    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }

    public int getStock() { return stock; }
    public void setStock(int stock) { this.stock = stock; }
}
```

Repository:

```java
package com.example.catalog;

import org.springframework.data.repository.CrudRepository;

public interface ProductRepository extends CrudRepository<Product, String> {
}
```

Example saving an entity:

```java
Product product = new Product("p-100", "Study Desk");
product.setOrigin(new Origin("Hanoi", "VN"));

product.getVariants().add(new Variant("DESK-BLACK", 12));
product.getVariants().add(new Variant("DESK-WHITE", 7));

product.getSpecifications().put("material", "wood");
product.getSpecifications().put("widthCm", "120");

product.getTags().add("furniture");
product.getTags().add("workspace");

productRepository.save(product);

Product loaded = productRepository.findById("p-100")
        .orElseThrow();

System.out.println(loaded.getVariants().get(0).getSku());
System.out.println(loaded.getSpecifications().get("material"));
System.out.println(loaded.getOrigin().getCity());
```

Assuming the application has configured a Redis connection and enabled Spring Data Redis repositories (via appropriate Spring Boot configuration or `@EnableRedisRepositories`), calling `save` converts the entire property graph using the active converter configuration; `findById` reconstructs the Java object from the data in Redis.

## 3. Mapping Nested Objects with Dot Notation

For an object property not marked as a separate reference, Spring Data Redis typically **flattens** the child object's simple properties into multiple hash fields:

```java
product.setOrigin(new Origin("Hanoi", "VN"));
```

Logical representation:

```text
origin.city    -> Hanoi
origin.country -> VN
```

When reading back, the converter uses these paths to reconstruct `Origin` and assign it to `Product.origin`.

How to visualize it:

```text
Product
└── origin
    ├── city     -> origin.city
    └── country  -> origin.country
```

The dot expresses traversal from parent property to child property, **not** a dynamic property-access operator like `product.origin.city` evaluated at runtime by Redis. Redis only stores field names as bytes alongside their corresponding values.

A few notable distinctions:

- **Flatten object:** child properties live directly inside the root entity's Redis Hash.
- **Store monolithic JSON:** if a custom converter is configured to write an object as a JSON string, Redis may hold only a single field containing the JSON content; sub-fields like `origin.city` no longer exist.
- **Store reference:** if using `@Reference`, that property can store reference info pointing to another object's key instead of flattening all fields of that object inside the current hash.

Thus, the field names shown here describe the typical mapping of **Spring Data Redis object mapping**. With custom converters, field names and encodings may differ.

## 4. Mapping `List` and Arrays: Paths Containing Indexes

`List` is an ordered collection. When a list is flattened into fields in a Redis Hash, each element typically carries an index:

```java
List<Variant> variants = List.of(
    new Variant("DESK-BLACK", 12),
    new Variant("DESK-WHITE", 7)
);
```

Logical representation:

```text
variants.[0].sku   -> DESK-BLACK
variants.[0].stock -> 12
variants.[1].sku   -> DESK-WHITE
variants.[1].stock -> 7
```

The path `variants.[0].stock` can be broken down into:

1. `variants`: collection property on `Product`.
2. `[0]`: first element.
3. `stock`: property of that element.

For a simple list:

```java
private List<String> photoUrls;
```

Logical representation:

```text
photoUrls.[0] -> https://example.org/images/1.jpg
photoUrls.[1] -> https://example.org/images/2.jpg
```

Note that **the index is a position**, not an immutable identity of the element. If you insert an element at the beginning of the list, the element previously at `[0]` shifts to `[1]` when the whole entity is saved again.

### 4.1. Why Not Just Use `LPUSH`?

Redis supports a native List structure with commands like `LPUSH`, `RPUSH`, `LRANGE`, `LSET`, etc. However, this code:

```java
product.getVariants().add(new Variant("DESK-RED", 3));
productRepository.save(product);
```

operates on a **Java collection inside a Redis Hash entity**. It is not equivalent to:

```redis
RPUSH products:p-100 "DESK-RED"
```

The `RPUSH` command requires the key to be a Redis List; in our example, `products:p-100` is a Redis Hash, so it would fail with a `WRONGTYPE` error.

If the domain requires frequent prepending/removing from head or tail, slicing ranges of long lists, or atomic per-element operations without rewriting the entity, consider **a separate Redis List model** managed with `ListOperations`, rather than assuming a `List` inside `@RedisHash` uses native List commands.

## 5. Mapping `Set`: Unique Elements Without Business Ordering

A Java `Set` represents a collection of unique elements according to equality rules. Example:

```java
Set<String> tags = new LinkedHashSet<>();
tags.add("workspace");
tags.add("furniture");
```

The object mapper can map elements using a collection representation in the hash, for instance:

```text
tags.[0] -> workspace
tags.[1] -> furniture
```

Do not attach business meaning to `[0]`, `[1]` when the source is a `Set`. `HashSet` has no element-ordering contract; even with `LinkedHashSet`, the Redis representation is not an API guaranteeing element positions like a Java List across every write.

Distinguish the two concepts:

| Java `Set` inside `@RedisHash` | Native Redis Set |
|---|---|
| An entity property, mapped by the converter when saving the entity | An independent Redis data type at its own key |
| Typically read/written together with the entity via repository | Manipulated via `SADD`, `SREM`, `SMEMBERS`, etc. |
| Field path `[n]` should not be treated as a stable ID | Suited for server-side membership checks and member add/remove |
| Entity TTL applies to the key holding the entity | Redis Set key TTL applies to the entire set |

If you just need to store a list of tags as part of a product, `Set<String>` inside the entity is natural. If you need millions of `SISMEMBER` checks and individual member updates, a separate Redis Set model may be more suitable.

## 6. Mapping `Map`: Paths Containing Keys in Square Brackets

Unlike `List`, `Map` looks up by **key**. Spring Data Redis uses the map key value in the field path:

```java
Map<String, String> specifications = new LinkedHashMap<>();
specifications.put("material", "wood");
specifications.put("widthCm", "120");
```

Logical representation:

```text
specifications.[material] -> wood
specifications.[widthCm]  -> 120
```

`[material]` here is **the key name**, not an index. Two maps with the same entries inserted in different orders are still keyed by map key rather than position.

### 6.1. Map Containing Objects

With `Map<String, Address>`, the path must express both **the map key name** and **the value's properties**:

```java
public class Address {
    private String city;
    private String street;

    public Address() { }

    public Address(String city, String street) {
        this.city = city;
        this.street = street;
    }

    public String getCity() { return city; }
    public void setCity(String city) { this.city = city; }

    public String getStreet() { return street; }
    public void setStreet(String street) { this.street = street; }
}
```

Suppose `Customer` has the field:

```java
private Map<String, Address> addresses;
```

And data:

```java
addresses.put("home", new Address("Da Nang", "Nguyen Van Linh"));
addresses.put("office", new Address("Hanoi", "Tran Duy Hung"));
```

Logical representation:

```text
addresses.[home].city      -> Da Nang
addresses.[home].street    -> Nguyen Van Linh
addresses.[office].city    -> Hanoi
addresses.[office].street  -> Tran Duy Hung
```

This is a multi-level path:

```text
Customer
└── addresses (Map)
    ├── ["home"] (Address)
    │   ├── city   -> addresses.[home].city
    │   └── street -> addresses.[home].street
    └── ["office"] (Address)
        ├── city   -> addresses.[office].city
        └── street -> addresses.[office].street
```

### 6.2. Maps with Complex Keys

Field paths in a Redis Hash must be formable as strings/bytes. Therefore, examples like `Map<String, ...>` with simple keys such as `"home"`, `"office"`, `"material"` are easier to understand and inspect.

If using `Map<UUID, ...>`, `Map<Enum, ...>`, or custom key types, ensure the converter has a suitable and symmetric way to convert **the map key** on write and read. Avoid assuming every Java object type turns into a valid field name without conversion.

Also, special characters in map key names (such as dots or square brackets) can make paths hard to read or interact unexpectedly with the mapper's path syntax. For arbitrary input data, define a stable key encoding convention or use an appropriate converter, then verify round-tripping under the exact deployed configuration.

## 7. Reading Paths from Redis CLI

After `productRepository.save(product)` saves the example product, you can inspect Redis using:

```redis
TYPE products:p-100
HGETALL products:p-100
HGET products:p-100 "name"
HGET products:p-100 "origin.city"
HGET products:p-100 "variants.[0].sku"
HGET products:p-100 "specifications.[material]"
```

`HGET` retrieves a field with the **exact** name. The Redis server does not inherently understand that `"variants.[0].sku"` means navigating into index 0 of a Java list; this name is **generated by the mapper before writing**.

If you try:

```redis
HGET products:p-100 "variants"
```

there is no guarantee Redis will return the whole list. Under the flattened model, the data lives across multiple `variants.[0].*`, `variants.[1].*` fields rather than a single `variants` field.

Likewise, `HGETALL` displays fields and values as stored by Redis—typically bytes interpreted as text by the CLI. The presence of `_class`, and how numbers, dates, or custom objects are serialized, can vary by converter/serializer. Use observed data on the running instance and version to determine the actual representation.

## 8. Property Paths Are a Mapping Convention, Not a Query Language

Three kinds of "paths" are frequently confused:

1. **Java property access:** `product.getVariants().get(0).getSku()`.
2. **Redis Hash field name:** `"variants.[0].sku"`.
3. **Repository queries:** methods like `findByName(...)`, which may require an index depending on the query type.

They are related, yet **not equivalent**. For example, you cannot assume that:

```java
interface ProductRepository extends CrudRepository<Product, String> {
    // No guarantee this acts as an arbitrary map/list query just from method naming:
    // List<Product> findBySpecificationsMaterial(String material);
}
```

will automatically query by `specifications.[material]` simply because that field exists in the Redis Hash. Redis repositories do not provide SQL or JSONPath over arbitrary hash fields. Secondary queries must rely on query derivation and indexing capabilities supported by Spring Data Redis; do not infer query capabilities from how the converter flattens fields.

If you need complex searches over map/list elements, choose a suitable indexing model, maintain a dedicated index, or use an appropriate search technology. `@Indexed` can be helpful for supported properties, but it does not turn the entire object graph into a multi-dimensional queryable structure.

## 9. Updating a Single Element and Re-saving the Entity

After reading an entity, modifying the Java object **does not mean** Redis is already updated:

```java
Product product = productRepository.findById("p-100")
    .orElseThrow();

product.getVariants().get(0).setStock(15);
product.getSpecifications().put("material", "bamboo");

productRepository.save(product);
```

At the application level, this reads the object, mutates two spots, and **re-saves the entity**. Spring Data Redis takes care of converting the object into its hash representation.

Do not mix:

```redis
HSET products:p-100 "variants.[0].stock" 15
```

with `productRepository.save(...)` without clearly establishing data ownership. A subsequent `save` can rewrite values from a stale object copy, overwriting the direct update; conversely, editing a field via CLI does not synchronize indexes or metadata managed by the repository.

For two concurrent requests:

```text
Request A                     Request B
---------                     ---------
Read Product (stock=12)       Read Product (stock=12)
Set stock=13                  Set stock=11
save(Product)                 save(Product)
```

The final outcome can reflect whichever save happened last instead of combining both changes. Object mapping does not automatically provide an "atomic inventory increment/decrement" contract. If business rules require accurate concurrent updates, use an appropriate data model and atomic operations—such as a separate counter with `INCRBY`, explicitly designed optimistic locking, or a Redis script as needed.

### 9.1. Adding, Removing, and Reordering Elements

With a list:

```java
product.getVariants().add(new Variant("DESK-RED", 3));
product.getVariants().remove(0);
productRepository.save(product);
```

Removing the first element shifts positions `[0]`, `[1]`. Do not store paths like `"variants.[0].sku"` in external systems to identify a SKU long-term. Rely on the `sku` field as the business identifier, or split variants into entities with their own IDs if they require independent updates, lookups, and lifecycle management.

With a map:

```java
product.getSpecifications().remove("widthCm");
productRepository.save(product);
```

After updating via the repository, the intended state is a property map reflecting the current map. Avoid assuming that manually editing a hash field has the same effect as updating the entire entity and auxiliary structures.

## 10. `null`, Empty Collections, and Missing Fields in a Hash

Three situations can carry different meanings in Java:

```java
product.setVariants(null);
product.setVariants(new ArrayList<>());
product.setVariants(List.of(new Variant("DESK-BLACK", 12)));
```

In a flattened Redis Hash, an **empty** collection may produce no indexed fields at all. `null` may also write no fields. Consequently, you cannot always distinguish "no data yet," "explicitly set to empty," and "set to null" merely by checking for `variants.[n]` fields in the hash. The value after reading back also depends on the constructor, property type, and active converter.

If the domain strictly must distinguish those three states, design an explicit signal:

```java
private boolean variantsLoaded;
private List<Variant> variants = new ArrayList<>();
```

or use an explicit domain state such as `NOT_LOADED`, `LOADED_EMPTY`, `LOADED_WITH_ITEMS`. Do not rely on the presence of a technical path when the domain needs to represent independent states.

### 10.1. `null` Values in a Map

A map containing an entry with a `null` value also needs to be weighed separately from a map **lacking that key**. Depending on converter policy, neither may produce a field. If those two states have different meanings, use a value object with a status flag or an explicit storage convention.

## 11. Serialization and Custom Conversions Change the Storage Structure

Spring Data Redis provides converters such as `MappingRedisConverter` to write and read fields based on domain type metadata. For types handled as *simple values*, the converter typically stores the data in a single field. For complex objects, the converter can traverse child properties to create multiple property paths.

However, a **custom converter** can choose to convert an entire object into a single field:

```text
Default flattened style:
  origin.city      -> Hanoi
  origin.country   -> VN

If a custom converter encodes Origin as a single value:
  origin           -> {"city":"Hanoi","country":"VN"}
```

This difference carries several consequences:

- `HGET key "origin.city"` is only useful if the mapper actually creates that field.
- An object containing JSON inside a hash does not automatically become RedisJSON with JSONPath.
- Changing converters after data has already been stored can cause read-back failures; consider compatibility and migration when changing schemas.
- If type metadata (such as `_class`) is used to restore subtypes, avoid arbitrarily deleting or altering it with raw Redis operations.

Field path formatting is a **mapping storage detail** and should not become a public interface between services when a repository/domain API can be used instead. When hash-field-level integration is genuinely required, formalize its schema and versioning.

## 12. TTL, Auxiliary Keys, and Expiration Scope

You can configure a TTL for the entire Redis entity:

```java
@RedisHash(value = "products", timeToLive = 1800)
public class Product {
    // Entity properties...
}
```

In this mapping model, the TTL applies to **the `products:<id>` key holding the Redis Hash**. That means `variants.[0].sku`, `origin.city`, and `specifications.[material]` all disappear together when the key expires; Spring Data Redis does not automatically give each Java List item or map entry an independent TTL just because they have separate paths.

Some newer Redis versions support setting expirations on individual hash fields, but that is a separate Redis feature and **does not mean** the TTL annotation on `@RedisHash` automatically gives each collection element its own expiration.

Besides the primary data key, the repository may create auxiliary keys to track the set of entity IDs, secondary indexes, or related metadata. Therefore:

- Do not assume `KEYS products:*` contains only Hashes representing a `Product`.
- Do not bulk-delete by prefix without understanding the auxiliary keys managed by the repository.
- When deleting an entity, prefer `productRepository.deleteById(id)` in repository-owned flows so related structures are handled by the repository mechanism.

## 13. When to Use Repository Mapping vs. Native Redis Structures?

| Need | Typically Suitable Model |
|---|---|
| Saving and retrieving a product object with several nested properties | `@RedisHash` + repository |
| Storing a small `List<Variant>` as part of product state | Collection property inside the entity |
| Very frequent head/tail mutations on a long list | Separate Redis List with `ListOperations` |
| Adding/removing members and checking membership on the Redis side | Separate Redis Set with `SetOperations` |
| Updating a counter concurrently across many threads | Separate Redis String/counter with atomic commands |
| Continuously looking up values by map key and updating entries independently | Separate Redis Hash with `HashOperations` |
| Deep searching/filtering across many properties and nested elements | Indexing model or suitable query solution |
| Keeping all properties in one lifecycle, saved and read as one object | Repository mapping |

If using `HashOperations` to store a standalone map:

```java
redisTemplate.opsForHash().put("product:specs:p-100", "material", "wood");
redisTemplate.opsForHash().put("product:specs:p-100", "widthCm", "120");
```

then this Redis Hash has direct fields `"material"` and `"widthCm"`. It is **not** the same mechanism as `Map<String, String> specifications` inside a `@RedisHash("products")` entity, where the field name might be `"specifications.[material]"`.

Both models use Redis Hashes, yet they have **different data boundaries and APIs**. Do not mix them just because the word "hash" appears in both.

## 14. Practice Example: Inspecting an Entity with Nested Paths

Create data via the repository as in Section 2, then inspect Redis:

```redis
TYPE products:p-100
HGETALL products:p-100
HGET products:p-100 "origin.city"
HGET products:p-100 "variants.[1].sku"
HGET products:p-100 "specifications.[material]"
```

Next, update the entity in Java:

```java
Product saved = productRepository.findById("p-100")
        .orElseThrow();

saved.getVariants().remove(0);
saved.getSpecifications().put("material", "bamboo");

productRepository.save(saved);
```

Inspect again:

```redis
HGETALL products:p-100
HGET products:p-100 "variants.[0].sku"
HGET products:p-100 "specifications.[material]"
```

Notice that the `"DESK-WHITE"` element previously at `[1]` may now be mapped at `[0]`, while the value for map key `"material"` changed to `"bamboo"`. This illustrates **positional access for lists** versus **keyed access for maps**.

If the fields in your instance do not match the example, first review your domain types, serializers, custom conversions, and Spring Data Redis version; do not rush to manually edit fields to match the illustration.

## 15. Common Design Pitfalls

**Confusing a Java List with a Redis List.** Seeing `List<Variant>` in an entity and calling `LRANGE products:p-100 0 -1` will not work if the actual key is a Redis Hash. Check the Redis type with `TYPE` and choose the matching API.

**Treating `[0]` of a list or set as a permanent ID.** When a list adds, removes, or reorders elements, indexes shift. Create business IDs for elements that need independent identification.

**Treating `"specifications.[material]"` as automatic query syntax.** It is merely a hash field path used by the mapper. Querying by value requires indexes or a supported data model.

**Updating the same data via both repository and raw `HSET`.** This easily causes overwrites, metadata drift, and skipped index updates. Establish a single API owner for the key's lifecycle.

**Assuming empty collections and `null` always store differently.** When data is flattened, missing fields do not necessarily tell you why. Represent business state with a dedicated property if needed.

**Setting an entity TTL and expecting each map entry to expire independently.** `@RedisHash` TTL applies to the entity key. If members need independent lifetimes, design separate keys or expiration mechanisms.

**Renaming Java properties while ignoring legacy data.** Renaming `specifications` to `details` makes the converter look for new paths while Redis still holds fields under the old names. Plan for compatibility or migration.

## 16. How to Visualize When Designing Entities

You can use the following rule to read a path like `orders.[0].attributes.[color]`:

```text
orders             -> collection property
.[0]               -> first element
.attributes        -> map property of the element
.[color]           -> value for key "color"
```

In a Redis Hash, that entire string is **one field name**. In Java, it is the result of traversing multiple property levels. In the repository, the converter bridges these two worlds.

When working with Spring Data Redis, decide upfront **which unit of data** should be stored, updated, and expired together. If `Product` and its child collections are usually read/written as one unit, repository mapping is very convenient. If individual elements need atomic updates, separate TTLs, native Redis commands, or specialized queries, split them into separate keys/data types suited to actual access patterns.

That is the crux of mapping collections, maps, and property paths: **Java defines the object structure; Spring Data Redis decides how to turn that structure into a Redis Hash; and Redis operates on the stored keys and hash fields**, rather than directly evaluating Java property-access expressions.
