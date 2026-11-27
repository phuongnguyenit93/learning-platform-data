# Text, Geospatial, Hashed, and Wildcard Indexes

## 1. Why Are Specialized Index Types Needed?

In the **Indexes** chapter of **Spring Data MongoDB**, standard indexes such as `{ tenantId: 1, createdAt: -1 }` work very well for equality conditions, value ranges, and sorting. However, many requirements go beyond comparing values of a single field:

- Finding products whose description contains **keywords**, ranked by relevance score.
- Finding pickup locations **near a user's coordinates** or **inside an area**.
- Distributing data more evenly across shards when a logical key has sufficient distinct values.
- Querying product attributes with a **dynamic** structure where field names cannot all be predicted upfront.

MongoDB provides specialized index types:

| Index type | Typical key pattern | Primary purpose |
|---|---|---|
**Text index** | `{ name: "text", description: "text" }` | Keyword search via `$text`; can compute `textScore` |
**Geospatial 2dsphere** | `{ pickupLocation: "2dsphere" }` | Point/region queries on Earth's surface using GeoJSON |
**Geospatial 2d** | `{ point: "2d" }` | Planar/legacy coordinates; does not replace 2dsphere for all use cases |
**Hashed index** | `{ customerId: "hashed" }` | Supports equality on hashed keys; often paired with hashed sharding strategies |
**Wildcard index** | `{ "attributes.$**": 1 }` | Indexes many dynamic field paths inside a document or map |

**No single type is the "strongest index".** Each type supports a specific family of queries and carries its own write costs and restrictions. Creating all four types on every collection can slow the system down due to index storage, cache pressure, and index maintenance overhead.

### Lesson Objectives

1. Explain the mechanics and use cases of text, geospatial, hashed, and wildcard indexes.
2. Write the corresponding MongoDB queries and recognize which index type actually supports them.
3. Create indexes via the MongoDB shell, Spring Data MongoDB metadata, or `MongoTemplate`/Java Driver as appropriate.
4. Distinguish `$text` from substring/regex matching and dedicated search solutions.
5. Read GeoJSON properly, including longitude–latitude order, distance units, and `2d` vs. `2dsphere`.
6. Understand hashed equality, shard key distribution, and range/unique/multikey limitations.
7. Use wildcard indexes for dynamic attributes while protecting field whitelists, tenant isolation, and performance.
8. Verify indexes via `getIndexes()`, `explain("executionStats")`, and integration tests against real MongoDB.

> Examples use Java 17+, Spring Boot 3.x, and Spring Data MongoDB 4.x. Certain capabilities depend on MongoDB server version: text/2dsphere date back to older releases, wildcard indexes arrived in MongoDB 4.2, and compound wildcard indexes have newer support bounds (MongoDB 7.0+). Always verify your deployed server/driver versions, topology, and API support; do not treat any shell snippet as guaranteed compatible with every environment.

## 2. Sample Data for the Four Index Types

We use a multi-tenant product catalog system. Products have text descriptions, pickup coordinates, customer/external IDs, and extensible attributes:

~~~json
{
  "_id": "p-101",
  "tenantId": "tenant-a",
  "customerId": "cust-100127",
  "name": "Steel water bottle",
  "description": "Insulated reusable water bottle for outdoor trips",
  "category": "DRINKWARE",
  "pickupLocation": {
    "type": "Point",
    "coordinates": [106.70098, 10.77689]
  },
  "attributes": {
    "material": "steel",
    "capacityMl": 500,
    "insulated": true
  }
}
~~~

In this schema:

- `name`/`description` are candidates for a **text index**.
- `pickupLocation` is a candidate for a **2dsphere index**.
- `customerId` can be a candidate for a **hashed index** when equality lookups and data distribution needs align.
- `attributes` holds properties varying by product category; it can be a candidate for a **wildcard index**.
- `tenantId` is a critical authorization boundary, **not optional** in tenant queries.

### 2.1. Spring Data MongoDB Entity

**CatalogProduct.java**

~~~java
package com.example.catalog;

import java.util.Map;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexType;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexed;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "catalog_products")
public class CatalogProduct {
    @MongoId(FieldType.STRING)
    private String id;

    private String tenantId;
    private String customerId;
    private String name;
    private String description;
    private String category;

    @GeoSpatialIndexed(type = GeoSpatialIndexType.GEO_2DSPHERE)
    private GeoJsonPoint pickupLocation;

    private Map<String, Object> attributes;

    protected CatalogProduct() {
        // For Spring Data materialization.
    }

    public CatalogProduct(
            String id, String tenantId, String customerId,
            String name, String description, String category,
            GeoJsonPoint pickupLocation,
            Map<String, Object> attributes) {
        this.id = id;
        this.tenantId = tenantId;
        this.customerId = customerId;
        this.name = name;
        this.description = description;
        this.category = category;
        this.pickupLocation = pickupLocation;
        this.attributes = attributes;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getCustomerId() { return customerId; }
    public String getName() { return name; }
    public String getDescription() { return description; }
    public String getCategory() { return category; }
    public GeoJsonPoint getPickupLocation() {
        return pickupLocation;
    }
    public Map<String, Object> getAttributes() {
        return attributes;
    }
}
~~~

`@MongoId(FieldType.STRING)` keeps `_id` as a BSON String. `GeoJsonPoint` takes **longitude first, latitude second**; `@GeoSpatialIndexed` describes a 2dsphere index at the metadata level, yet **the index is not necessarily created automatically**: that depends on auto-index configuration and deployment workflows.

In this lesson, text, hashed, and wildcard examples are created explicitly for clarity; **do not simultaneously enable an uncontrolled auto-creation mechanism that creates conflicting definitions**.

## 3. Text Index: Word-Based Search, Not Arbitrary Substrings

A MongoDB text index builds index entries for **terms** extracted from text fields using the server's tokenization and language processing rules.

~~~javascript
db.catalog_products.createIndex(
  {
    name: "text",
    description: "text"
  },
  {
    name: "idx_product_text",
    weights: {
      name: 5,
      description: 1
    },
    default_language: "english"
  }
);
~~~

This index covers two fields yet remains a **single text index**. MongoDB enforces a limit of **at most one traditional text index per collection**; you can include multiple fields inside that single text index definition. Do not try to create one text index for `name` and another separate text index for `description` on the same collection.

### 3.1. Querying with $text

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  $text: {
    $search: "water bottle"
  }
});
~~~

Under standard text search interpretation, terms inside `$search` do not automatically perform a **substring** match like SQL `LIKE '%water bottle%'`. MongoDB matches terms, language-based word stems, and search syntax rules.

Compare **distinct** requirements:

| Requirement | Suggested mechanism |
|---|---|
Find terms `water` or `bottle` in content | MongoDB `$text` |
Prioritize exact phrase `"water bottle"` | Text search with phrase quoting syntax |
Exact name match `"Steel water bottle"` | Equality/collation or standard index per contract |
Match substring `"ottl"` anywhere | Do not treat text index as a substring index |
Character-by-character autocomplete | Dedicated search (e.g., MongoDB Search) or custom design |
Typo/fuzzy search, synonyms, rich ranking | Dedicated search engine/search index |

**Key point:** a text index does not cover every search requirement. When autocomplete, fuzzy matching, language-specific analyzers, or advanced ranking are required, evaluate **MongoDB Search** (Atlas Search in applicable environments) or a dedicated search service; that is a different index/search architecture from standard `createIndex({ field: "text" })`.

### 3.2. Phrases, Negation, and Token Semantics

Examples in mongosh:

~~~javascript
// Match an exact phrase enclosed in double quotes.
db.catalog_products.find({
  $text: { $search: "\"water bottle\"" }
});

// Match term water while excluding documents containing term plastic.
db.catalog_products.find({
  $text: { $search: "water -plastic" }
});
~~~

The search string syntax has special rules for quotes, minus signs, and terms. Never concatenate an untrusted search query directly and assume it acts purely as a literal keyword. Define API policies for quoting, negation, length limits, and special characters.

### 3.3. Why Might a Text Index Not Help Regex Queries?

~~~javascript
db.catalog_products.find({
  name: /bottle/i
});
~~~

This is a regex query, **not `$text`**. A text index is not built to accelerate arbitrary regexes, especially unanchored or collation-incompatible regexes. Anchored prefix queries on a B-tree index under suitable conditions behave very differently from `$text` or full-scan regexes.

## 4. Text Score, Field Weights, and Result Ordering

When multiple documents match keywords, applications often want higher-relevance matches first. MongoDB exposes `textScore` metadata:

~~~javascript
db.catalog_products.find(
  {
    tenantId: "tenant-a",
    $text: { $search: "water bottle" }
  },
  {
    name: 1,
    description: 1,
    score: { $meta: "textScore" }
  }
).sort({
  score: { $meta: "textScore" }
});
~~~

`weights: { name: 5, description: 1 }` makes term matches in the name weigh differently from matches in the description. However, **scores are not probabilities** and do not sit on a fixed "0 to 100" scale. Do not set arbitrary business score cutoffs without testing against real data.

### 4.1. Score Does Not Automatically Appear on Every Find

`$text` results do not store a permanent `score` field inside the original BSON document. `score` is generated from `$meta: "textScore"` metadata in projection/sort, not an application field persisted to the collection.

If a DTO needs the relevance score, `@TextScore` in Spring Data MongoDB can be used on supported mapping paths; verify in practice how the query requests and materializes the score.

### 4.2. Text Search and Sorting by Date

An endpoint may want:

- **Relevance-first:** sort `textScore DESC`.
- **Newest-first:** filter with `$text` and sort `createdAt DESC`.
- **Hybrid ranking:** requires an explicit formula combining relevance, freshness, and quality.

Do not assume a text index works like a compound B-tree index capable of pre-sorting arbitrary additional fields. When sorting by another field, the server may need a separate sort step. Measure with `explain`.

## 5. Language, Stemming, Stop Words, and Vietnamese Text

Traditional MongoDB text indexes have a **language** setting for stemming and stop words. The index language governs how terms are stored; the `$text` language governs how searches are parsed.

Example:

~~~javascript
db.catalog_products.createIndex(
  { name: "text", description: "text" },
  {
    name: "idx_product_text_none",
    default_language: "none"
  }
);
~~~

This is an **alternative** to `idx_product_text` from section 3, **not a second command to run alongside an existing text index on the same collection**. Changing default language or weights requires a managed index replacement migration.

With `default_language: "none"`, MongoDB skips language-specific stemming and stop-word filtering. It can suit multilingual data or when no stemmer fits, yet it **does not provide specialized Vietnamese word segmentation, diacritic folding, spellchecking, or synonyms**.

### 5.1. Vietnamese Text Requires Dedicated Testing

Content such as:

~~~text
"Bình giữ nhiệt bằng thép không gỉ"
~~~

is not guaranteed to match queries with stripped diacritics, reordered words, or partial characters the way users expect. Never pick `default_language: "english"` assuming Vietnamese words will be tokenized accurately.

If your application requires:

- Matching with or without diacritics;
- Vietnamese word segmentation;
- Per-character autocomplete;
- Domain-specific merchandising synonyms;
- Typo correction or fuzzy ranking;

evaluate a search solution with suitable analyzers. Build a realistic Vietnamese query test suite to benchmark result quality before finalizing your architecture.

### 5.2. Operational Limitations

- A collection can have only one traditional text index, though that index can span multiple fields.
- Text indexes are built on **text fields**, not arbitrary numeric/object structures.
- Traditional text indexes have special **collation** rules (on collections with a non-simple default collation, `{ locale: "simple" }` must be considered when creating a text index).
- `$text` has specific rules inside aggregation pipelines and cannot substitute for geospatial queries.
- Check MongoDB release notes before combining with views, sharded collections, or special operators.

**Do not treat a text index as the default choice for SKU fields.** SKU codes have token-splitting quirks and usually call for equality/prefix lookups with standard indexes or dedicated search schemas.

## 6. Text Indexes in Spring Data MongoDB

Spring Data MongoDB provides `@TextIndexed` to mark fields included in a text index and `TextCriteria`/`TextQuery` to construct `$text` queries.

### 6.1. `@TextIndexed` Metadata

Inside an **entity class** having `name` and `description` fields:

~~~java
import org.springframework.data.mongodb.core.index.TextIndexed;

@TextIndexed(weight = 5)
private String name;

@TextIndexed
private String description;
~~~

This is an **illustrative field snippet**, not a standalone Java class. When using auto-index creation or an index resolver in a controlled migration step, Spring Data can use this text index metadata to construct the index definition.

If you already created a text index via MongoDB shell/driver, prevent the app from accidentally creating a second conflicting text index on the same collection. **One unified index-management strategy** matters more than choosing annotations vs. shell scripts.

### 6.2. TextCriteria and TextQuery

**CatalogTextSearchService.java**

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.TextCriteria;
import org.springframework.data.mongodb.core.query.TextQuery;
import org.springframework.stereotype.Service;

@Service
public class CatalogTextSearchService {
    private final MongoTemplate mongo;

    public CatalogTextSearchService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public List<CatalogProduct> search(
            String authenticatedTenantId,
            String searchTerm,
            int limit) {
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || searchTerm == null || searchTerm.isBlank()
                || searchTerm.length() > 100
                || limit < 1 || limit > 100) {
            throw new IllegalArgumentException("Invalid filter");
        }

        TextCriteria criteria = TextCriteria
                .forDefaultLanguage()
                .matching(searchTerm);

        TextQuery query = TextQuery
                .queryText(criteria)
                .sortByScore();

        query.addCriteria(
                Criteria.where("tenantId").is(authenticatedTenantId));
        query.limit(limit);

        return mongo.find(query, CatalogProduct.class);
    }
}
~~~

`TextQuery.sortByScore()` requests sorting by text relevance. Depending on API/version, `@TextScore` on entities/DTOs can map the score. This example returns the entity directly and **does not expose score** as a regular persisted field.

**Security note:** `authenticatedTenantId` must come from server-side authentication. `$text` is a search filter, not a substitute for tenant isolation or product visibility permissions.

### 6.3. When Should You Avoid `TextQuery`?

`TextQuery` targets MongoDB's traditional text search. For autocomplete, fuzzy search, highlighting, language-specific analyzers, and complex custom ranking, evaluate another search engine. Never try to force Querydsl/repositories or `TextQuery` to express features unsupported by the adapter or server.

## 7. Geospatial: Spatial Data and 2dsphere

Geospatial indexes support queries by **location, distance, and geometry**. For real-world geographic coordinates (longitude/latitude on Earth), the standard choice is `2dsphere`:

~~~javascript
db.catalog_products.createIndex(
  { pickupLocation: "2dsphere" },
  { name: "idx_product_pickup_2dsphere" }
);
~~~

GeoJSON Point document:

~~~json
{
  "type": "Point",
  "coordinates": [106.70098, 10.77689]
}
~~~

In GeoJSON, `coordinates` are ordered **[longitude, latitude]**; never `[latitude, longitude]`. Document this convention across DTOs, validation, and integration tests to avoid subtle bugs where swapped numbers still look like valid floats.

### 7.1. Validating Coordinates

- Longitude normally spans **−180 to +180** degrees.
- Latitude spans **−90 to +90** degrees.
- Data sources must share a consistent coordinate reference system; GeoJSON on 2dsphere uses WGS84 geographic coordinates.
- `0,0` does not mean "location unknown". Use missing/null fields per schema policy instead of defaulting to zero coordinates.
- GeoJSON geometries must match valid structures (`Point`, `Polygon`, etc.), including closed rings for polygons.

### 7.2. `2dsphere` Differs from `2d`

| Aspect | `2dsphere` | `2d` |
|---|---|---|
Space | Earth / spherical geometry | 2D flat plane |
Typical data | GeoJSON Point, LineString, Polygon | Legacy coordinate pairs / planar |
Index | `{ location: "2dsphere" }` | `{ point: "2d" }` |
Common queries | `$near`/`$nearSphere` and `$geoWithin` with compatible geometry | `$near`/`$geoWithin` on compatible legacy/planar coordinates |
Distance unit | GeoJSON points on Earth's surface: typically **meters** | Depends on planar coordinate system, not automatically geographic meters |
When to choose | Store/delivery locations with longitude/latitude | Flat maps or legacy schemas designed accordingly |

Do not mechanically swap `"2d"` for `"2dsphere"` if existing data does not match GeoJSON or spherical coordinate conventions. For new geographic location features, **GeoJSON + 2dsphere** is generally clearer.

### 7.3. Missing Fields and `2dsphere` Indexes

`2dsphere` exhibits sparse-like behavior: documents lacking a valid location value do not generate an entry in the index. Consequently, geo queries only match documents whose geometries are indexed.

Never assume a product absent from a geo query does not exist: the product may exist while lacking `pickupLocation`, having invalid coordinates, or lying outside the search radius/region.

## 8. Proximity Queries with `$near`

Find products within a radius around a GeoJSON Point:

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  pickupLocation: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      $maxDistance: 3000
    }
  }
});
~~~

Here, with a GeoJSON Point and `2dsphere` index, `$maxDistance: 3000` means **3,000 meters**. `$near` returns matching documents ordered nearest-first; there is no need for an extra sort on raw coordinates to achieve "nearest".

### 8.1. Do Not Compare Distances Using Degree Differences

Computing:

~~~text
deltaLon = abs(106.72 - 106.70)
deltaLat = abs(10.79 - 10.77)
~~~

does not measure ground distance in meters. A degree of longitude changes physical length with latitude; Earth is not a uniform flat longitude–latitude grid. Use proper geospatial operators instead of rolling Euclidean distance over raw degrees.

### 8.2. Radius and Distance Units

When using GeoJSON/2dsphere with `$near`, distances are in **meters**. For operators taking legacy coordinate pairs or `$centerSphere`, units may be **radians** instead of meters; never reuse the same `3000` constant across different geo operators blindly.

If an API requirement states "within 2.5 km", convert it to **2500 meters** for GeoJSON `$near`; verify with tests covering nearby points, points outside the radius, and points right on the boundary.

### 8.3. Nearest Queries Do Not Filter Tenants Automatically

`$near` evaluates only spatial relationships. Forgetting `tenantId` or product status allows an endpoint to leak unauthorized pickup points. Combine geo predicates with **tenant and authorization filters** on the server.

## 9. `$geoWithin`, Polygons, and `$geoNear`

### 9.1. Finding Within a Region Using `$geoWithin`

Example GeoJSON polygon (illustrative coordinates, not real administrative boundaries):

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  pickupLocation: {
    $geoWithin: {
      $geometry: {
        type: "Polygon",
        coordinates: [[
          [106.69, 10.77],
          [106.72, 10.77],
          [106.72, 10.79],
          [106.69, 10.79],
          [106.69, 10.77]
        ]]
      }
    }
  }
});
~~~

A polygon requires a **closed ring**: the starting coordinate repeats at the end. For complex polygons, consider ring winding order, self-intersections, large areas, and MongoDB geometric semantics; never trust arbitrary client-supplied polygons without validation.

`$geoWithin` tests **containment inside an area**, which does not automatically sort results nearest-first. If the UI needs nearest-first ordering, compute/sort distances separately.

### 9.2. `$geoNear` Aggregation Stage

`$geoNear` outputs the **calculated distance** into a result field:

~~~javascript
db.catalog_products.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      distanceField: "distanceMeters",
      maxDistance: 3000,
      spherical: true,
      key: "pickupLocation",
      query: {
        tenantId: "tenant-a",
        category: "DRINKWARE"
      }
    }
  },
  { $project: {
      _id: 1,
      name: 1,
      distanceMeters: 1
    }
  },
  { $limit: 20 }
]);
~~~

In this pipeline:

- `$geoNear` must be the **first stage** in the pipeline per stage rules.
- `distanceField` generates the distance value for DTOs/UI.
- `query` inside `$geoNear` applies tenant and category filters.
- `key` disambiguates the geo field if the collection has multiple geospatial indexes.
- `maxDistance` uses units matching GeoJSON/configuration—here, meters.

Do not place `$match` before `$geoNear` just to filter tenant: put it in `$geoNear.query` since `$geoNear` must come first.

### 9.3. Limits When Combining Text Search and `$geoNear`

A single pipeline cannot place both `$geoNear` and a `$match` containing `$text` in the **first** position that each requires. If a feature needs combined text relevance and spatial distance ranking, evaluate dedicated search engines, controlled multi-step queries, or MongoDB Search depending on your environment's capabilities.

Do not treat `$text` + `$near` as a general-purpose query supported across all server versions and indexes. Check operator restrictions and align ranking semantics.

## 10. GeoJSON and Spring Data MongoDB

Spring Data supports `GeoJsonPoint`, `GeoJsonPolygon`, `Criteria`, `NearQuery`, and `MongoTemplate.geoNear(...)` across its corresponding APIs.

### 10.1. `GeoJsonPoint` and `nearSphere`

**CatalogGeoSearchService.java**

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class CatalogGeoSearchService {
    private final MongoTemplate mongo;

    public CatalogGeoSearchService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public List<CatalogProduct> nearby(
            String authenticatedTenantId,
            double longitude,
            double latitude,
            double radiusMeters,
            int limit) {
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || !Double.isFinite(longitude)
                || !Double.isFinite(latitude)
                || longitude < -180 || longitude > 180
                || latitude < -90 || latitude > 90
                || !Double.isFinite(radiusMeters)
                || radiusMeters <= 0 || radiusMeters > 10000
                || limit < 1 || limit > 100) {
            throw new IllegalArgumentException("Invalid geo query");
        }

        Query query = Query.query(
                Criteria.where("tenantId").is(authenticatedTenantId)
                        .and("pickupLocation")
                        .nearSphere(new GeoJsonPoint(
                                longitude, latitude))
                        .maxDistance(radiusMeters));

        query.limit(limit);
        return mongo.find(query, CatalogProduct.class);
    }
}
~~~

`nearSphere` on `GeoJsonPoint` expresses a proximity query. With GeoJSON + 2dsphere, `radiusMeters` specifies the meter bound under the corresponding query semantics; verify the generated BSON and test distance boundaries on your Spring Data version.

**Important:** this method does not accept arbitrary geo field names from clients; it fixes `pickupLocation` and takes tenant from the authenticated context. `radiusMeters` is capped to avoid overly broad scans from a single request.

### 10.2. When Distance Is Needed in the Results

`MongoTemplate.geoNear(...)` returns `GeoResults<T>` containing `GeoResult<T>` entries with `Distance`:

~~~java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;
import org.springframework.data.mongodb.core.aggregation.NearQuery;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;

NearQuery near = NearQuery
        .near(new GeoJsonPoint(106.70098, 10.77689))
        .maxDistance(new Distance(3, Metrics.KILOMETERS))
        .spherical(true);

GeoResults<CatalogProduct> results =
        mongo.geoNear(near, CatalogProduct.class);
~~~

This is an **illustrative snippet within a scope having `mongo` of type `MongoTemplate`**. For a multi-tenant endpoint, add the tenant filter to `NearQuery`'s query/filter per your version's API, or use `$geoNear.query` explicitly; never copy a tenantless demo snippet into production.

Distance is a **computed** value, not a field stored in the entity. When returning it in an API, normalize units and round per contract (meters/km) rather than exposing an unlabeled number.

## 11. Hashed Indexes: Optimizing Equality on Hashed Values

A hashed index stores a hash of the field value inside the index structure. Example:

~~~javascript
db.catalog_products.createIndex(
  { customerId: "hashed" },
  { name: "idx_product_customer_hashed" }
);
~~~

Suitable query:

~~~javascript
db.catalog_products.find({
  customerId: "cust-100127"
});
~~~

A hashed index supports **equality lookups**, but does not preserve the original ordering of IDs to serve range or sort queries on that field.

### 11.1. Cases Where Hashed Should Not Be Used

~~~javascript
// Range on customerId strings.
db.catalog_products.find({
  customerId: { $gte: "cust-100000" }
});

// Sort ascending by customerId.
db.catalog_products.find({}).sort({
  customerId: 1
});
~~~

These queries are not well served by a hashed index in natural `customerId` order. If an API frequently scans key ranges or paginates sorted by ID, an ascending/descending B-tree index is more appropriate.

### 11.2. Hashed Indexes Do Not Enforce Uniqueness

MongoDB **does not support unique hashed indexes** with the semantics of a unique B-tree index. Even though hashes spread values out, business uniqueness cannot rely on hashing.

If `customerId` must be unique per tenant, create an appropriate unique index, for example:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, customerId: 1 },
  { unique: true, name: "uq_tenant_customer" }
);
~~~

This is a **different** index from the hashed index; evaluate whether both are genuinely needed. Never call `createIndex({ customerId: "hashed" }, { unique: true })` expecting MongoDB to enforce uniqueness.

### 11.3. Hashed and Arrays

A hashed index cannot be a multikey index across multi-element arrays. If the indexed field becomes an array, MongoDB enforces constraints rejecting that data type in many scenarios. Choose a **stable scalar key** (String, ObjectId, suitable numeric types, etc.) rather than `List<String>` as a hashed key.

## 12. Hashed Indexes and Sharding: Check Cardinality First

One motivation for hashed keys is **distributing data and write traffic** across a sharded collection. For example, monotonically increasing event IDs can create a hot shard under range sharding; a hashed shard key spreads IDs across hash ranges.

Conceptual diagram:

~~~mermaid
flowchart LR
    A["Sequential Event IDs"] --> B["Hash shard key"]
    B --> C["Hash range A"]
    B --> D["Hash range B"]
    B --> E["Hash range C"]
    C --> F["Shard 1"]
    D --> G["Shard 2"]
    E --> H["Shard 3"]
~~~

However:

1. **Creating a hashed index does not enable sharding**. Administrators must configure the sharded collection and shard key via MongoDB's sharding mechanism.
2. **Cardinality matters**. If there are only three `tenantId` values with millions of documents each, hashing `tenantId` still yields only three hash values; even distribution cannot be expected.
3. **Equality keys enable targeted routing** when the shard key is supplied; queries omitting the shard key may scatter across all shards.
4. **Range locality trades off against distribution**. Hashed shard keys fit point-ID access better than ordered range scans.
5. **Uniqueness and hashed shard keys** carry specific rules on sharded collections; do not assume a regular non-shard-key unique index enforces cluster-wide uniqueness.

### 12.1. When Is `customerId` a Good Hashed Key?

If `customerId` has millions of distinct values and each customer owns a moderate number of documents, hashed distribution helps avoid write hotspots from sequential keys. Yet if a single `customerId` generates 40% of write traffic, **hashing never splits identical values into different hashes**; the hot key persists.

Never select a shard key from a theoretical distribution chart alone. Analyze document size, write patterns, read targeting, tenant isolation, transactions, migrations, and resharding strategies.

### 12.2. Compound Hashed Indexes

In MongoDB versions that support it, a compound hashed index combines regular fields with one hashed field, for example:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, customerId: "hashed" },
  { name: "idx_tenant_customer_hashed" }
);
~~~

Do not treat a compound hashed index as unique and do not assume every server version accepts the same key pattern. When designing sharding, also inspect **shard key order**, distribution balance, and query routing.

## 13. Wildcard Indexes: When Field Names Vary Per Document

Suppose product types carry custom attributes:

~~~json
{
  "_id": "p-bottle",
  "attributes": {
    "material": "steel",
    "capacityMl": 500,
    "insulated": true
  }
}
~~~

~~~json
{
  "_id": "p-shirt",
  "attributes": {
    "size": "M",
    "fabric": "cotton",
    "color": "blue"
  }
}
~~~

Manually creating an index for **every** custom field name is infeasible when there are thousands of attributes. A wildcard index indexes paths beneath `attributes`:

~~~javascript
db.catalog_products.createIndex(
  { "attributes.$**": 1 },
  { name: "idx_product_attributes_wildcard" }
);
~~~

Queries eligible for this index include:

~~~javascript
db.catalog_products.find({
  "attributes.material": "steel"
});

db.catalog_products.find({
  "attributes.capacityMl": { $gte: 500 }
});

db.catalog_products.find({
  "attributes.fabric": "cotton"
});
~~~

**A wildcard index indexes BSON field paths**, not full-text search across strings or a `2dsphere` substitute for spatial fields.

### 13.1. `$**` vs. `attributes.$**` Syntax

| Key pattern | Scope |
|---|---|
`{ "$**": 1 }` | Wildcard across document paths (per MongoDB indexing rules) |
`{ "attributes.$**": 1 }` | Scoped to nested fields inside `attributes` |

For products, a scoped wildcard `attributes.$**` is usually easier to manage: it avoids accidentally indexing fields outside dynamic attributes like descriptions or internal metadata.

**Do not treat a wildcard index as an ideal compound B-tree index for every sort.** It has its own structure and limitations and works best when a dynamic attribute is a primary filter predicate.

### 13.2. A Wildcard Index Does Not Optimize Every AND Automatically

A query:

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  "attributes.material": "steel",
  "attributes.capacityMl": { $gte: 500 }
})
.sort({ createdAt: -1 });
~~~

will not automatically get tight bounds on all predicates plus free sorting from a wildcard index. Inspect explain for index bounds, residual filters, and `SORT`. For frequently queried attributes, a dedicated field index or different data model may perform better.

### 13.3. Compound Wildcard Indexes: Check Server Version

On MongoDB servers supporting **compound wildcard indexes** (MongoDB 7.0+), you can combine a structured prefix with a wildcard field:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, "attributes.$**": 1 },
  { name: "idx_tenant_attributes_wildcard" }
);
~~~

This is a **version-dependent example**, not a command guaranteed to run on MongoDB 4.2/5.0/6.0. Constraints on field position, sorting, multikey, and wildcard paths must be verified against your server release. On older servers, combine a standalone wildcard index with a suitable tenant index and measure residual filtering costs, or adjust the schema design.

## 14. Wildcard Indexes and Limitations to Know

### 14.1. Dynamic Flexibility Has a Cost

A wildcard index can generate many index entries for the actual paths present in each document. If every product has a map of thousands of attributes, index size and update costs can grow substantially.

It excels for **unpredictable fields**, yet is not inherently faster than fixed indexes when workloads hit a few hot fields. Compare:

- 90% of queries target `attributes.material` → a dedicated field index may be simpler.
- Queries spread across hundreds of category-specific fields → wildcard adds real value.
- Queries always include tenant + sort by createdAt → may require pairing with other index plans or server versions supporting compound wildcard under applicable constraints.

### 14.2. Arrays, Nested Documents, and Null

Values inside `attributes` can be scalars, arrays, or nested documents. Wildcard indexing on nested arrays follows specific rules for **indexed paths, bounds, and sort eligibility**. Never assume a query on an array of documents guarantees predicates apply to **the same element**.

Example:

~~~json
{
  "attributes": {
    "variants": [
      { "color": "RED", "stock": 2 },
      { "color": "BLUE", "stock": 12 }
    ]
  }
}
~~~

Dot-path query:

~~~javascript
{
  "attributes.variants.color": "RED",
  "attributes.variants.stock": { $gte: 10 }
}
~~~

can match **two different elements**. If you require a single RED variant with stock at least 10, use `$elemMatch`:

~~~javascript
db.catalog_products.find({
  "attributes.variants": {
    $elemMatch: {
      color: "RED",
      stock: { $gte: 10 }
    }
  }
});
~~~

Indexes—including wildcard and multikey—**never replace writing accurate predicates**.

### 14.3. Do Not Use Wildcard as a Substitute for Unique, Text, or Geospatial

A wildcard index must not be treated as creating **unique constraints across all dynamic fields**. Nor should you expect it to support `$text` ranking or GeoJSON `$near` like dedicated indexes.

When business logic needs:

- Unique SKU → unique B-tree/compound index on the exact business key.
- Full-text term matching → text index or dedicated search index.
- Distance/region → 2dsphere.
- Dynamic attributes filtered primarily by equality/range → wildcard is a candidate.

Do not use `{ "$**": 1 }` as a "universal optimizer for every query" merely because it covers many fields.

## 15. Decision Table: Choosing Indexes by Query Shape

| Common query | Candidate index | Misconception to avoid |
|---|---|---|
`$text: { $search: "bottle" }` | Text on name/description | Not arbitrary substring search |
`$near` with GeoJSON Point | 2dsphere on location | Not a B-tree index on longitude |
`$geoWithin` polygon | 2dsphere | Does not sort nearest-first by default |
`customerId = X`, high-cardinality key | Hashed may fit | Does not support range/sort or unique like B-tree |
`customerId >= X` with sort | B-tree index on customerId | Hashed destroys original key ordering |
`attributes.material = "steel"` | Wildcard or dedicated field index | Not full-text search |
Querying many dynamic attributes per tenant | Wildcard/compound wildcard per version | Does not auto-optimize all ANDs/sorts |
`tenantId + sku` must be unique | Unique compound B-tree | Never replace with hashed unique |
Newest products by tenant/status | Compound B-tree with equality + sort | Text/geo/wildcard are not default substitutes |

### Short Decision Tree

~~~mermaid
flowchart TD
    A["Query goal"] --> B{"By location/distance?"}
    B -->|"Yes"| C["2dsphere / 2d matching coordinate system"]
    B -->|"No"| D{"By text terms?"}
    D -->|"Yes"| E["Text index or dedicated Search"]
    D -->|"No"| F{"By unpredictable dynamic fields?"}
    F -->|"Yes"| G["Wildcard / dedicated index for hot fields"]
    F -->|"No"| H{"Equality on key needing distribution?"}
    H -->|"Yes"| I["Consider hashed + sharding analysis"]
    H -->|"No"| J["Single/compound B-tree"]
    C --> K["Explain and measure on real workload"]
    E --> K
    G --> K
    I --> K
    J --> K
~~~

A single collection can use **multiple index types**, provided each index has a clear justification and overall operational costs are weighed.

## 16. Creating and Listing Indexes via MongoTemplate and Java Driver

In Spring Data MongoDB, `MongoTemplate.indexOps(...)` works cleanly for standard indexes and supported metadata. For specialized key patterns like `"text"`, `"hashed"`, and `"$**"`, using the underlying MongoDB Java Driver via `MongoTemplate` sometimes expresses exact BSON cleanly across builder version variations.

**CatalogSpecialIndexProvisioner.java**

~~~java
package com.example.catalog;

import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.IndexOptions;
import java.util.ArrayList;
import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Component;

@Component
public class CatalogSpecialIndexProvisioner {
    private final MongoTemplate mongo;

    public CatalogSpecialIndexProvisioner(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    // Execute through managed migration/provisioning,
    // never on every HTTP request.
    public void ensureSpecialIndexes() {
        MongoCollection<Document> collection =
                mongo.getCollection("catalog_products");

        collection.createIndex(
                new Document("name", "text")
                        .append("description", "text"),
                new IndexOptions()
                        .name("idx_product_text")
                        .weights(new Document("name", 5)
                                .append("description", 1)));

        collection.createIndex(
                new Document("pickupLocation", "2dsphere"),
                new IndexOptions().name("idx_pickup_2dsphere"));

        collection.createIndex(
                new Document("customerId", "hashed"),
                new IndexOptions().name("idx_customer_hashed"));

        collection.createIndex(
                new Document("attributes.$**", 1),
                new IndexOptions().name("idx_attributes_wildcard"));
    }

    public List<Document> listRawIndexes() {
        MongoCollection<Document> collection =
                mongo.getCollection("catalog_products");
        List<Document> indexes = new ArrayList<>();
        collection.listIndexes().into(indexes);
        return indexes;
    }
}
~~~

This is **illustrative provisioning** code. In production, define an index-management strategy, creation permissions, option-drift checks, index-build windows, and rollback plans. `createIndex` can throw if an index name exists with a different definition or if the server rejects a key pattern.

### 16.1. Do Not Mix Every Index API Uncoordinatedly

If an entity has `@GeoSpatialIndexed` and auto-index creation is enabled while a migration also creates an index on that field, you can produce duplicate indexes or name/option conflicts. Pick **one primary source of truth for index definitions**, such as controlled migrations.

Spring Data specialized annotations/DSLs like `@TextIndexed` and `@GeoSpatialIndexed` are useful for metadata; when a newer feature exists only in certain server/driver releases, evaluate raw BSON on your exact runtime version.

### 16.2. Inspecting Created Indexes Accurately

In mongosh:

~~~javascript
db.catalog_products.getIndexes();
~~~

Fields to verify:

1. `name`: matches the intended index name.
2. `key`: contains `"text"`, `"2dsphere"`, `"hashed"`, or `"attributes.$**"` as appropriate.
3. `weights`/`default_language` for text indexes.
4. `2dsphereIndexVersion` or specialized metadata, if returned by the server.
5. `unique`/`partialFilterExpression`/`collation` if configured.

**Text index note:** MongoDB may store `key` using internal representations such as `_fts` and `_ftsx` instead of literal `{ name: "text", description: "text" }`. Tests should check metadata like `weights`/`name`/type appropriately instead of asserting literal input key patterns across all versions.

## 17. Explain: Checking Which Index Each Query Uses

Creating an index is only step one. An index may exist while the planner picks another index or COLLSCAN.

### 17.1. Text

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  $text: { $search: "water bottle" }
})
.explain("executionStats");
~~~

Inspect the text search plan, documents examined, and returned count. Plans may show text-specific stage names depending on MongoDB version; do not simply grep for `IXSCAN` and conclude a text index isn't working.

### 17.2. Geo

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  pickupLocation: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      $maxDistance: 3000
    }
  }
})
.explain("executionStats");
~~~

Geo stages may appear as `GEO_NEAR` or specialized stage structures depending on server version. Check which geospatial index was chosen, keys/documents examined, and total time; documents outside the radius also affect execution cost.

### 17.3. Hashed

~~~javascript
db.catalog_products.find({
  customerId: "cust-100127"
})
.explain("executionStats");
~~~

Compare against a B-tree index on `customerId` if the workload also needs ranges or sorts. Small collections or low selectivity may cause the planner not to favor the hashed index.

### 17.4. Wildcard

~~~javascript
db.catalog_products.find({
  "attributes.material": "steel"
})
.explain("executionStats");
~~~

Observe index name, key bounds, `totalKeysExamined`, `totalDocsExamined`, `nReturned`, and whether a blocking sort occurs. A query on `attributes.capacityMl` may receive a different plan despite sharing the same wildcard index.

### 17.5. Do Not Judge from a Single Metric

| Metric / Observation | What to understand |
|---|---|
`nReturned` | How many documents were output |
`totalKeysExamined` | How many index keys were inspected |
`totalDocsExamined` | How many documents were accessed |
`executionTimeMillis` | Explain run execution time, not production p95 |
`COLLSCAN` | Can be reasonable on very small collections |
Blocking `SORT` | Can consume significant memory/CPU on large sets |
Matching index name | Insufficient if keys/docs scanned remain huge |
Index unused | May stem from query shape, stats, cache, collation, or tiny dataset |

Measure on representative data, especially across tenants with skewed product counts. Do not turn on `hint` just to force an index that "looks right" without measuring the full trade-offs.

## 18. Integration Testing Against Real MongoDB

Mocking `MongoTemplate` verifies service calls, but cannot prove:

- The text index was created and `$text` actually matches terms.
- GeoJSON stores coordinates in the right order and `2dsphere` serves `$near`.
- The hashed index exists with the right definition and is not mistaken for unique.
- The wildcard index has the expected key pattern.
- Tenant filters are enforced in queries.

Use a real test MongoDB (such as Testcontainers). Spring Boot 3.x `@DataMongoTest` **does not start a MongoDB server automatically**.

### 18.1. Test Seeding Three Products and Four Indexes

**CatalogSpecialIndexesTest.java**

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import com.mongodb.client.model.IndexOptions;
import java.util.List;
import java.util.Map;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
@Import({
        CatalogTextSearchService.class,
        CatalogGeoSearchService.class
})
class CatalogSpecialIndexesTest {
    @Autowired MongoTemplate mongo;
    @Autowired CatalogTextSearchService textSearch;
    @Autowired CatalogGeoSearchService geoSearch;

    @BeforeEach
    void prepare() {
        // Drop collection only on an isolated test database.
        mongo.dropCollection(CatalogProduct.class);
        var collection = mongo.getCollection("catalog_products");

        // Explicitly manage indexes in test: avoid duplicating
        // with entity auto-index-creation.
        collection.createIndex(
                new Document("name", "text")
                        .append("description", "text"),
                new IndexOptions().name("idx_product_text"));
        collection.createIndex(
                new Document("pickupLocation", "2dsphere"),
                new IndexOptions().name("idx_pickup_2dsphere"));
        collection.createIndex(
                new Document("customerId", "hashed"),
                new IndexOptions().name("idx_customer_hashed"));
        collection.createIndex(
                new Document("attributes.$**", 1),
                new IndexOptions().name("idx_attributes_wildcard"));

        mongo.insert(List.of(
                new CatalogProduct(
                        "p-101", "tenant-a", "cust-101",
                        "Steel water bottle",
                        "Insulated reusable water bottle",
                        "DRINKWARE",
                        new GeoJsonPoint(106.70098, 10.77689),
                        Map.of("material", "steel", "capacityMl", 500)),
                new CatalogProduct(
                        "p-102", "tenant-a", "cust-102",
                        "Ceramic mug",
                        "Hot drink mug",
                        "DRINKWARE",
                        new GeoJsonPoint(106.72000, 10.79000),
                        Map.of("material", "ceramic", "capacityMl", 250)),
                new CatalogProduct(
                        "p-201", "tenant-b", "cust-201",
                        "Water bottle",
                        "Travel bottle",
                        "DRINKWARE",
                        new GeoJsonPoint(106.70100, 10.77690),
                        Map.of("material", "steel", "capacityMl", 750))
        ), CatalogProduct.class);
    }

    @Test
    void textSearchUsesTenantFilter() {
        List<CatalogProduct> result =
                textSearch.search("tenant-a", "water bottle", 10);

        assertThat(result).extracting(CatalogProduct::getId)
                .containsExactly("p-101");
    }

    @Test
    void geoQueryExcludesNearbyProductFromOtherTenant() {
        List<CatalogProduct> result =
                geoSearch.nearby(
                        "tenant-a",
                        106.70098, 10.77689,
                        5000, 20);

        assertThat(result).extracting(CatalogProduct::getId)
                .containsExactly("p-101", "p-102");
    }

    @Test
    void wildcardDynamicFieldQueryReturnsExpectedProduct() {
        Query query = Query.query(
                Criteria.where("tenantId").is("tenant-a")
                        .and("attributes.material").is("steel"));

        List<CatalogProduct> result =
                mongo.find(query, CatalogProduct.class);
        assertThat(result).extracting(CatalogProduct::getId)
                .containsExactly("p-101");
    }

    @Test
    void hashedFieldCanBeQueriedByEquality() {
        Query query = Query.query(
                Criteria.where("customerId").is("cust-102")
                        .and("tenantId").is("tenant-a"));

        List<CatalogProduct> result =
                mongo.find(query, CatalogProduct.class);
        assertThat(result).extracting(CatalogProduct::getId)
                .containsExactly("p-102");
    }

    @Test
    void specializedIndexDefinitionsExistOnServer() {
        List<Document> indexes =
                mongo.getCollection("catalog_products")
                        .listIndexes()
                        .into(new java.util.ArrayList<>());

        assertThat(indexes).extracting(
                document -> document.getString("name"))
                .contains(
                        "idx_product_text",
                        "idx_pickup_2dsphere",
                        "idx_customer_hashed",
                        "idx_attributes_wildcard");

        Document geo = indexes.stream()
                .filter(i -> "idx_pickup_2dsphere"
                        .equals(i.getString("name")))
                .findFirst().orElseThrow();
        assertThat(geo.get("key", Document.class)
                .getString("pickupLocation")).isEqualTo("2dsphere");

        Document hash = indexes.stream()
                .filter(i -> "idx_customer_hashed"
                        .equals(i.getString("name")))
                .findFirst().orElseThrow();
        assertThat(hash.get("key", Document.class)
                .getString("customerId")).isEqualTo("hashed");
    }
}
~~~

**What this test proves:**

- Text search matches using the created index without leaking `tenant-b` results.
- Geospatial query returns the two `tenant-a` points within radius, nearest first.
- Querying dynamic field `attributes.material` returns the expected document.
- Equality queries on the hashed key work properly.
- Geo/hashed indexes exist with the right key types.

**What this test does not prove:** with three documents, the planner may pick COLLSCAN on some queries; this test is not a benchmark. Nor does it prove good shard-key distribution in production. The text example uses English terms to verify mechanics; Vietnamese search quality must be tested separately.

### 18.2. Additional Cases to Cover

| Test case | Expectation |
|---|---|
Text index does not exist yet | `$text` may error; never silently fall back to regex |
Changing weights or default language | Must go through index migration, not two competing text indexes |
Two text docs with differing relevance | Verify score/ranking on exact server version |
Vietnamese terms with/without diacritics | Document limitations and analyzer strategy |
Swapped longitude and latitude | Tests catch wrong point or validation failure |
Point outside `maxDistance` | Excluded from results |
Missing/null/invalid GeoJSON field | Clear policy across queries, indexes, and ingestion |
`$geoWithin` polygon | Returns only documents inside valid polygon |
Hashed key is an array | Verify hashed/multikey limits and write errors |
Hashed index + range/sort | Do not assume index provides original ordering |
Two tenants share business ID | Do not expect hashed index to enforce uniqueness |
Wildcard with previously unseen dynamic field | New query still considers index if schema/index fit |
Wildcard nested array | Verify `$elemMatch` same-element matching |
Changing index options/definition with same name | Migration handles conflicts explicitly |
Parallel test execution | Isolate databases/collections |

## 19. Performance and Maintenance Cost of the Four Indexes

Specialized indexes still consume resources. Whenever a product is inserted or updated:

- **Text index:** changing `name`/`description` requires updating term entries.
- **2dsphere:** changing location/geometry updates spatial index entries.
- **Hashed:** changing `customerId` recomputes the hash and updates entries.
- **Wildcard:** changing `attributes` with many nested fields can update many entries.

### 19.1. What Should Benchmarks Measure?

| Metric | Meaning |
|---|---|
Read p50/p95/p99 | Real latency per query shape |
`totalKeysExamined` | Index key scan volume |
`totalDocsExamined` | FETCH/document read volume |
`nReturned` | Documents actually returned |
Index disk/cache footprint | Resources consumed by indexes |
Insert/update throughput | Price paid to maintain indexes |
Build time | Migration cost on large collections |
Text search relevance | Result quality beyond raw speed |
Geo distance correctness | Accuracy of distances, coordinates, and radii |
Sharding distribution | Data and traffic balance across shards |
Wildcard dynamic-field coverage | Ratio of queries served by index vs. residual filters |

There is no fixed formula like "wildcard is always X times slower than normal index" or "hashed is always faster than B-tree". Results depend on cardinality, data shape, workload, and server topology.

### 19.2. Avoiding Unnecessary Indexes

Suppose a single collection simultaneously has:

~~~javascript
{ name: "text", description: "text" }
{ pickupLocation: "2dsphere" }
{ customerId: "hashed" }
{ "attributes.$**": 1 }
{ tenantId: 1, category: 1, createdAt: -1 }
~~~

This set may be justified if the application truly executes all five distinct query types, or it may be excessive if nearly all requests just filter by tenant/category.

Workflow:

1. Collect real query shapes and frequencies.
2. Inventory existing indexes, including text/geo indexes created via annotations.
3. Choose candidates matching operator requirements.
4. Benchmark reads, writes, and index sizes.
5. Deploy only indexes showing clear net benefit.
6. Monitor `$indexStats` over a representative window; do not drop indexes solely from short-term low counts.

## 20. Security and Correctness in Specialized Queries

### 20.1. Tenant Isolation Applies to Text and Geo Too

Wrong:

~~~javascript
db.catalog_products.find({
  $text: { $search: "water bottle" }
});
~~~

Right for multi-tenant data:

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  $text: { $search: "water bottle" }
});
~~~

The same rule applies to `$near`, `$geoNear.query`, and dynamic attribute filters. **An index is not an authorization boundary**; a well-indexed query that omits `tenantId` still leaks data.

### 20.2. Whitelist Dynamic Fields

Never accept raw HTTP requests like:

~~~json
{
  "fieldPath": "anything.from.client",
  "operator": "$regex",
  "value": ".*"
}
~~~

and pass them straight into a BSON query. With wildcard indexes, it is tempting to allow arbitrary client-supplied paths. Enforce strict controls on:

- Which attributes may be queried (`material`, `capacityMl`, `color`, etc.).
- Which operators are permitted (`eq`, bounded ranges, etc.).
- Allowed data types and value bounds for each attribute.
- Text search length, geo radius, result limits, and timeouts.
- Tenant scope and server-side authorization policies.

In Java, use an enum or `switch` to map allowed attribute names onto fixed paths instead of interpolating client strings:

~~~java
String fieldPath = switch (requestedAttribute) {
    case "material" -> "attributes.material";
    case "capacityMl" -> "attributes.capacityMl";
    case "color" -> "attributes.color";
    default -> throw new IllegalArgumentException(
            "Attribute not allowed for filtering");
};

Query query = Query.query(
        Criteria.where("tenantId").is(authenticatedTenantId)
                .and(fieldPath).is(validatedValue));
~~~

This snippet illustrates code inside a service with authenticated/validated `requestedAttribute`, `authenticatedTenantId`, and `validatedValue`, not a standalone Java file. Validate value types before binding them to the query.

### 20.3. Location and Privacy

Location can be sensitive personal data. Avoid logging raw personal coordinates, addresses, or geo queries in production unless authorized. If the app only needs nearby stores, avoid retaining precise user coordinates longer than business needs require.

Never serialize full GeoJSON payloads or internal customer fields in API responses when only product name, distance, and public attributes are needed. Define explicit response DTO whitelists.

## 21. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
Treating text index as a substring index | Search misses expected matches | Distinguish term, phrase, regex, and autocomplete |
Creating two text indexes on one collection | Index build fails | Combine fields into a single text index |
Ignoring text language configuration | Wrong tokenization/stemming for data | Configure language, test Vietnamese, consider Search |
Treating `textScore` as a probability | Flawed ranking or cutoffs | Measure relevance; do not treat score as % |
Forgetting `$meta: "textScore"` when score is needed | No relevance score returned | Add projection/sort metadata properly |
Running arbitrary regex expecting text index speedup | COLLSCAN or broad scan | Design matching query/search index |
Swapping longitude/latitude | Matches wrong location | Enforce `[longitude, latitude]` and test |
Confusing meters with radians | Huge radius errors | Check GeoJSON vs. legacy operators |
Assuming `$geoWithin` sorts nearest-first | Wrong UI ordering | Use geoNear or compute/sort distances |
Forgetting `$geoNear` must be first in pipeline | Aggregation fails | Place stage first and filter inside `query` |
Assuming `2d` fits all geographic GeoJSON on Earth | Wrong coordinate/geometry semantics | Use `2dsphere` |
Calling hashed index a unique index | Duplicate business keys | Add a separate unique B-tree/compound index |
Using hashed for range/sort | Cannot use natural order | Use a standard ordered index |
Hashing low-cardinality `tenantId` to balance shards | Hot keys/shards persist | Analyze cardinality and shard key |
Thinking creating a hashed index shards data | Data stays unsharded | Sharding requires separate cluster admin |
Putting an array in a hashed key | Violates indexed type rules | Use a stable scalar key |
Using wildcard to replace text/2dsphere | Lacks specialized operator semantics | Pick the dedicated index type |
Creating document-wide `$**` wildcard recklessly | Huge index, slow writes | Scope to `attributes.$**` and measure |
Assuming compound wildcard works on old MongoDB | Index command unsupported | Check server version (7.0+) |
Assuming wildcard optimizes every AND/sort | Expensive residual filter/SORT | Explain and add dedicated indexes for hot fields |
Allowing arbitrary client field paths | Security and heavy-query risks | Whitelist allowed fields and operators |
Forgetting tenant filter in text/geo queries | Leaks cross-tenant data | Bind auth-context tenant into BSON |
Testing only with mocks | Unknown whether index/geo/text works | Integration test against real MongoDB |
Inferring performance solely because index exists | Planner may not pick the index | Run explain and benchmarks |

## 22. Practice Exercises

**Exercise 1 — Basic text.** Create a text index on `name`/`description`, run `$text` searching `water bottle`, and compare results with equality and regex. Explain why the three lookups are not equivalent.

**Exercise 2 — Weights and score.** Give `name` a higher weight than `description`. Seed one doc matching in `name` and another matching in `description`; inspect `textScore` and verify relevance ordering. Never treat score as a percentage probability.

**Exercise 3 — Vietnamese text.** Seed documents with `Bình giữ nhiệt`, `bình giữ nhiệt`, and an unaccented variant. Compare behavior under language settings / `"none"` in a test database, document limitations, and propose suitable analyzers/search tools.

**Exercise 4 — GeoJSON Point.** Seed two nearby points and one distant point. Run `$near` with a radius in meters; intentionally swap lon/lat in a test to catch coordinate bugs.

**Exercise 5 — GeoWithin Polygon.** Create a closed polygon and find points inside/outside the boundary. Test an invalid polygon and define API validation rules.

**Exercise 6 — GeoNear distance.** Use `$geoNear` to compute `distanceMeters` while filtering tenant inside `query`. Compare nearest-first ordering against unsorted `$geoWithin`.

**Exercise 7 — Hashed equality.** Create `{ customerId: "hashed" }`, test equality, range, and sort, and inspect explain. Explain why hashed indexes cannot enforce unique business constraints.

**Exercise 8 — Shard key.** Simulate 100,000 sequential event IDs under two shard key designs: range vs. hashed. Evaluate key distribution, query targeting, and range access rather than looking only at shard count.

**Exercise 9 — Wildcard attributes.** Create products with varying dynamic fields. Index `attributes.$**` and query `material`, `capacityMl`, and `fabric`. Compare against a dedicated index on the most frequently queried field.

**Exercise 10 — Wildcard and arrays.** Add an `attributes.variants` array and compare dot-path queries vs. `$elemMatch`. Demonstrate that an index does not fix cross-element matching bugs.

**Exercise 11 — Compound wildcard.** On MongoDB 7.0+ in test, create `{ tenantId: 1, "attributes.$**": 1 }` and compare queries with and without tenant. If your environment is older, document the version constraint and alternative design.

**Exercise 12 — Spring Data mapping.** Add `@GeoSpatialIndexed`, use `GeoJsonPoint` and `Criteria.nearSphere`, and write `TextQuery` with tenant filtering. Verify raw BSON and query results on real MongoDB.

**Exercise 13 — Index migration.** Intentionally create a text index with different language/weights, then update metadata. Design a migration process without creating two competing text indexes, ensuring rollback and measuring build cost.

**Exercise 14 — Benchmark.** Seed a large dataset across multiple tenants and dynamic attributes. Measure p95 for text/geo/hashed/wildcard, `keysExamined`/`docsExamined`, index sizes, and before/after insert/update throughput. Decide which indexes to keep or drop from real measurements.

## 23. Key Takeaways

A **text index** serves **term search** via `$text` and supports `textScore`, but is not a general-purpose substring, autocomplete, or fuzzy search engine. Manage language settings, field weights, and consider dedicated search for Vietnamese or complex ranking.

**Geospatial indexes** require exact coordinate systems and operators. For geographic locations, **GeoJSON + 2dsphere** supports distance/region queries; always store `[longitude, latitude]`, check meter vs. radian units, bound search radii, and filter tenants in the database.

**Hashed indexes** suit **equality** lookups on high-cardinality keys and can support hashed sharding designs; they **do not enable sharding automatically**, do not replace unique indexes, and do not support range/sort in original order. **Wildcard indexes** support dynamic fields like `attributes.*`, yet do not optimize all AND/sort shapes, do not replace text/geo, and can generate many index entries.

In **Spring Data MongoDB**, use the right tool for each job: `TextCriteria`/`TextQuery`, `GeoJsonPoint`/`Criteria`, `@TextIndexed`/`@GeoSpatialIndexed` metadata, and `MongoTemplate`/Java Driver for specialized BSON definitions. **Accept an index design only after verifying the index physically exists, query results are accurate, security filters are enforced, and `explain("executionStats")`/benchmarks succeed on representative workloads.**
