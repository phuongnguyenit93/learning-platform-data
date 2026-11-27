# Product Catalog: Variable Attributes and Filter Queries in MongoDB

An e-commerce catalog rarely has a single fixed data structure for every product. Laptops have **RAM, SSD capacity, screen size, CPU**; phones have **cellular network, camera, battery capacity**; shoes have **color, size, material**; food items have **weight, expiration date, ingredients**. Meanwhile, the application still needs to search, filter by multiple conditions, paginate, sort by price, and display **dynamic filters (facets)** suited to the category being viewed.

MongoDB supports flexible documents, making it well-suited for attributes that vary by product type. However, **flexibility does not mean storing everything in an arbitrary object and querying it arbitrarily will remain fast**. Field structure, value representation, the attribute definition system, index types, variant storage placement, and query construction must be designed cohesively.

Target example:

> In the laptop category, find active products from the Acer brand with at least 16 GB of RAM and a price of at most 30 million VND, sorted by ascending price; at the same time, display the product counts corresponding to filters such as brand, RAM capacity, and storage drive.

This lesson belongs to the **Application Design** chapter and focuses on **modeling product catalogs with variable attributes and filter queries** in MongoDB. The examples use mock data in a test database and are not production configuration defaults.

## 1. Learning Objectives

After this lesson, learners can:

1. Distinguish between **common attributes**, **category-specific attributes**, **variant/SKU attributes**, and **search-oriented attributes**.
2. Design MongoDB documents for products across multiple types without creating a separate collection for every small product group.
3. Compare the **dynamic subdocument**, **key–value array Attribute Pattern**, and **hybrid schema** models.
4. Standardize attribute names, value types, units of measurement, range representations, and valid value sets.
5. Write filters using **equality, $in, range, $elemMatch, $all** without mixing up conditions across different array elements.
6. Design **multikey indexes**, regular indexes, wildcard indexes, and indexes for common queries.
7. Build **faceted search** with aggregation, understanding self-excluding facets and pagination.
8. Separate **product** from **variant/SKU** to filter color/size/inventory on the exact matching attribute pair.
9. Construct safe queries in the **Java MongoDB Sync Driver** and **Spring Data MongoDB**, avoiding accepting arbitrary operators/fields from users.
10. Test data, tune explain/latency, and roll out attribute extensions across multiple application versions.

## 2. Domain Language to Align On

| Concept | Meaning | Example |
|---|---|---|
| **Product** | A logical product for display | Laptop Acer A14 |
| **Category** | Product classification group | laptops, phones, shoes |
| **Attribute/Specification** | Descriptive property | ramGB = 16 |
| **Facet** | Dimension that can be filtered and show counts | RAM: 8/16/32 GB |
| **Variant/SKU** | Variation that can be sold/ordered individually | Black shoe size 41 |
| **Inventory** | Sellable quantity of a SKU/location | SKU-001 has 5 left |
| **Offer/Price** | Price, currency, promotion/availability by channel | 22,000,000 VND |
| **Search document** | Record optimized for search/listing | Brand, category, search attributes |
| **Attribute definition** | Configuration defining type and filter behavior | ramGB: number, min/max |

Do not confuse:

- **Product ID** with **SKU ID**: a single product can have multiple SKUs.
- **Display price** with **final checkout price**: prices change by channel/promotion/time.
- **Aggregate inventory** with **specific variant inventory**: having black size 40 in stock does not mean black size 41 is in stock.
- **Facet count** with **stock quantity**: a facet can count products, SKUs, or offers; the unit of measurement must be clearly defined.

## 3. Questions to Answer Before Designing the Schema

Before choosing a document shape, write down the list of real queries:

~~~text
GET /products?category=laptops&brand=Acer&ramGBMin=16&maxPrice=30000000
GET /products?category=phones&storageGB=256
GET /products?category=shoes&color=black&sizeEU=41&inStock=true
GET /products?category=laptops&sort=price_asc&pageSize=24
GET /products/{id}
GET /categories/{id}/facets
~~~

Key decisions:

- How many categories will new products belong to? Which attributes does each category have?
- Which fields are **very frequently filtered**, and which are only displayed on the detail page?
- When a user selects multiple values in the same facet, is it **OR** or **AND**?
- Do attributes have numeric, date, String, Boolean, or array types?
- Do price and inventory live on the product, SKU, offer, or across multiple stores?
- Should facets update dynamically based on filtered results, or only show fixed counts per category?
- Are there multiple tenants/sellers/countries/currencies?
- What are the latency targets, product counts, update frequencies, and result set sizes?

**The schema should derive from actual queries and business rules**, not merely from the fact that MongoDB allows nested documents.

## 4. Sample Dataset Used Throughout

Create the **catalog_lab** database and **products** collection in a learning environment. The examples below use integer prices in **VND**, avoiding Double for monetary values.

~~~javascript
use catalog_lab

db.products.insertMany([
  {
    _id: "L-101",
    tenantId: "SHOP-A",
    categoryId: "laptops",
    brandId: "acer",
    title: "Acer Swift A14",
    status: "ACTIVE",
    visibility: "PUBLIC",
    priceVnd: NumberLong("22000000"),
    attributes: {
      ramGB: 16,
      storageGB: 512,
      screenInch: 14,
      color: "black"
    }
  },
  {
    _id: "L-102",
    tenantId: "SHOP-A",
    categoryId: "laptops",
    brandId: "lenovo",
    title: "Lenovo IdeaPad S",
    status: "ACTIVE",
    visibility: "PUBLIC",
    priceVnd: NumberLong("16000000"),
    attributes: {
      ramGB: 8,
      storageGB: 256,
      screenInch: 15.6,
      color: "gray"
    }
  },
  {
    _id: "L-103",
    tenantId: "SHOP-A",
    categoryId: "laptops",
    brandId: "dell",
    title: "Dell X Pro",
    status: "ACTIVE",
    visibility: "PUBLIC",
    priceVnd: NumberLong("33000000"),
    attributes: {
      ramGB: 16,
      storageGB: 1024,
      screenInch: 15.6,
      color: "silver"
    }
  },
  {
    _id: "L-104",
    tenantId: "SHOP-A",
    categoryId: "laptops",
    brandId: "acer",
    title: "Acer Creator 16",
    status: "ACTIVE",
    visibility: "PUBLIC",
    priceVnd: NumberLong("40000000"),
    attributes: {
      ramGB: 32,
      storageGB: 1024,
      screenInch: 16,
      color: "black"
    }
  },
  {
    _id: "P-101",
    tenantId: "SHOP-A",
    categoryId: "phones",
    brandId: "samsung",
    title: "Samsung Mobile 256",
    status: "ACTIVE",
    visibility: "PUBLIC",
    priceVnd: NumberLong("17000000"),
    attributes: {
      ramGB: 8,
      storageGB: 256,
      batteryMAh: 5000,
      color: "black"
    }
  },
  {
    _id: "S-101",
    tenantId: "SHOP-A",
    categoryId: "shoes",
    brandId: "puma",
    title: "Puma Runner",
    status: "ACTIVE",
    visibility: "PUBLIC",
    priceVnd: NumberLong("1800000"),
    attributes: {
      material: "mesh",
      gender: "unisex"
    }
  },
  {
    _id: "S-102",
    tenantId: "SHOP-A",
    categoryId: "shoes",
    brandId: "nike",
    title: "Nike Runner",
    status: "ACTIVE",
    visibility: "PUBLIC",
    priceVnd: NumberLong("2400000"),
    attributes: {
      material: "synthetic",
      gender: "unisex"
    }
  },
  {
    _id: "L-X",
    tenantId: "SHOP-B",
    categoryId: "laptops",
    brandId: "acer",
    title: "Other tenant laptop",
    status: "ACTIVE",
    visibility: "PUBLIC",
    priceVnd: NumberLong("10000000"),
    attributes: {
      ramGB: 64,
      storageGB: 2048,
      color: "black"
    }
  }
]);
~~~

**Note:** the IDs are fixed, so only insert once on a clean lab collection. Never drop a production collection to re-run examples.

### 4.1. Illustrative Query Results

Filtering only for **SHOP-A**, category **laptops**, status ACTIVE, visibility PUBLIC:

| ID | Brand | RAM (GB) | Storage (GB) | Price (VND) |
|---|---|---:|---:|---:|
| L-101 | acer | 16 | 512 | 22,000,000 |
| L-102 | lenovo | 8 | 256 | 16,000,000 |
| L-103 | dell | 16 | 1024 | 33,000,000 |
| L-104 | acer | 32 | 1024 | 40,000,000 |

When filtering **brand=acer**, **RAM ≥ 16 GB**, **price ≤ 30,000,000 VND**, only **L-101** remains.

### 4.2. Isolate Tenant Scope from the Start

L-**X** is a product in the same category/brand but belongs to **SHOP-B**. This is an intentional test record: a query relying only on category/brand while forgetting **tenantId** could accidentally return another tenant's product.

The tenantId values for user requests must be obtained from a trusted **authentication/authorization context**, rather than allowing clients to assert permissions via a query parameter alone.

## 5. Model 1: Dynamic Attributes Subdocument

The main document uses:

~~~javascript
{
  _id: "L-101",
  categoryId: "laptops",
  attributes: {
    ramGB: 16,
    storageGB: 512,
    screenInch: 14,
    color: "black"
  }
}
~~~

A shoe product might have:

~~~javascript
{
  _id: "S-101",
  categoryId: "shoes",
  attributes: {
    material: "mesh",
    gender: "unisex"
  }
}
~~~

Advantages:

- Very easy to read: **attributes.ramGB**, **attributes.storageGB**.
- Specific indexes can be created for popular fields.
- Numeric attributes remain numbers, enabling proper range queries.
- Only stores fields that actually exist on the product, avoiding dozens of null fields.
- Well-suited when the number of categories and attribute sets are governed.

Limitations:

- The number of keys can grow rapidly across product verticals.
- Dynamic queries on new attributes are hard to pre-index.
- Near-duplicate keys such as **ram**, **memoryGB**, **ramGB** easily cause fragmented data.
- Each category needs type/unit rules; MongoDB does not validate them automatically unless a validator is configured.
- A wildcard index can help with unpredictable fields, but does not replace every purpose-built compound index.

### 5.1. Querying with Dotted Paths

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  categoryId: "laptops",
  status: "ACTIVE",
  visibility: "PUBLIC",
  brandId: "acer",
  "attributes.ramGB": { $gte: 16 },
  priceVnd: { $lte: NumberLong("30000000") }
}).sort({ priceVnd: 1, _id: 1 });
~~~

Expected result: **L-101**.

### 5.2. Specifying That a Field Exists or Has a Valid Type

~~~javascript
db.products.find({
  categoryId: "laptops",
  "attributes.ramGB": { $type: "number" }
});
~~~

The **number** type in $type is a general alias for matching BSON numeric types. Do not mix **"16"** (String) and **16** (Number), because numeric range filters may not behave as expected when data is stored with the wrong type.

### 5.3. Limitations of Dynamic Key Names

In object form, keys are part of the BSON structure. Do not accept raw field names or operator expressions from clients and concatenate them directly into a query:

~~~text
User input: arbitrary path/operator
Application: string-concatenate into query
Result: query semantics go beyond allowed facets
~~~

Look up attributes via an allowlisted **attribute definition registry**, validate types, and only construct registered dotted paths.

## 6. Model 2: Key–Value Array Attribute Pattern

Another option is to represent attributes as elements in an array:

~~~javascript
{
  _id: "L-101",
  categoryId: "laptops",
  attributes: [
    { key: "ramGB", valueNum: 16 },
    { key: "storageGB", valueNum: 512 },
    { key: "screenInch", valueNum: 14 },
    { key: "color", valueStr: "black" }
  ]
}
~~~

This is the **Attribute Pattern** commonly used when there are many kinds of metadata that need filtering by attribute name and value.

### 6.1. Why Separate valueNum and valueStr?

In this design, an element holds a **typed value**:

~~~javascript
{ key: "ramGB", valueNum: 16 }
{ key: "color", valueStr: "black" }
{ key: "waterResistant", valueBool: true }
~~~

If a single **value** field holds both String and Number, range queries and indexing become harder to manage. Separating value fields clarifies the schema, though a registry is still needed to define which key has which type, prevent duplicate keys, and standardize units.

### 6.2. Matching One Condition with $elemMatch

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  categoryId: "laptops",
  attributes: {
    $elemMatch: {
      key: "ramGB",
      valueNum: { $gte: 16 }
    }
  }
});
~~~

**$elemMatch** ensures that **key=ramGB** and **valueNum≥16** belong to **the same element** of the attributes array.

### 6.3. Why Two Dotted-Notation Conditions Can Be Wrong

Document:

~~~javascript
{
  attributes: [
    { key: "ramGB", valueNum: 8 },
    { key: "storageGB", valueNum: 1024 }
  ]
}
~~~

Semantically buggy query:

~~~javascript
db.products.find({
  "attributes.key": "ramGB",
  "attributes.valueNum": { $gte: 16 }
});
~~~

MongoDB can match this because one element has **key=ramGB**, while another element has **valueNum≥16**. This is a false positive.

Use:

~~~javascript
db.products.find({
  attributes: {
    $elemMatch: {
      key: "ramGB",
      valueNum: { $gte: 16 }
    }
  }
});
~~~

### 6.4. Matching Two Different Attributes Simultaneously

To require **RAM≥16** and **storage≥512**, you must require **two corresponding elements**:

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  categoryId: "laptops",
  attributes: {
    $all: [
      {
        $elemMatch: {
          key: "ramGB",
          valueNum: { $gte: 16 }
        }
      },
      {
        $elemMatch: {
          key: "storageGB",
          valueNum: { $gte: 512 }
        }
      }
    ]
  }
});
~~~

**$all** combines multiple **$elemMatch** conditions for the same array; each condition can be satisfied by a different element. This is an AND across attributes.

### 6.5. Multiple Values in One Facet Are Usually OR

For example, color **black or gray**:

~~~javascript
{
  attributes: {
    $elemMatch: {
      key: "color",
      valueStr: { $in: ["black", "gray"] }
    }
  }
}
~~~

| Intent | Logic |
|---|---|
| Minimum 16 RAM and minimum 512 SSD | AND across two attributes |
| Color black or gray | OR within one facet |
| Brand Acer or Dell | $in on brandId |
| Has both Wi-Fi and Bluetooth | AND if business logic requires both |
| Size 41 black **same SKU** | AND within one variant, not across two separate arrays |

### 6.6. Advantages and Trade-offs

Advantages:

- Can use a compound multikey index on key and typed value.
- Convenient for generating dynamic facets with **$unwind + $group**.
- Has room for per-attribute metadata if genuinely needed.
- Does not create a new BSON path for every key.

Trade-offs:

- Larger documents due to repeating key names.
- Queries are easy to get wrong if $elemMatch is forgotten.
- Multi-attribute AND may not leverage indexes optimally for all conditions.
- Compound multikey indexes have restrictions with multiple array paths.
- Requires validation so duplicate key elements do not appear unintentionally.

## 7. Model 3: Hybrid Schema

An operationally practical solution combines **fixed fields** for common queries, strongly typed **searchable attributes**, and flexible **specs** rarely used for filtering:

~~~javascript
{
  _id: "L-101",
  tenantId: "SHOP-A",
  categoryId: "laptops",
  brandId: "acer",
  status: "ACTIVE",
  visibility: "PUBLIC",
  priceVnd: NumberLong("22000000"),
  searchable: {
    ramGB: 16,
    storageGB: 512,
    color: "black"
  },
  specs: {
    cpuModel: "Intel Core example",
    panelType: "IPS",
    ports: ["USB-C", "HDMI"],
    keyboardLayout: "US"
  }
}
~~~

**searchable** is a data convention for filtering; MongoDB does not automatically create a search index for that field.

Hybrid usually fits well when most requests only filter **category + brand + price + status**, while each vertical has a few important facets such as RAM/SSD for laptops or color/size for shoes.

A source of truth must be defined if a piece of information appears in both **searchable** and **specs**, avoiding stale copies.

## 8. Choosing a Model via Comparison Table

| Criterion | attributes object | Attribute Pattern array | Hybrid |
|---|---|---|---|
| Document readability | Very good | Moderate | Good |
| Exact/range queries on common fields | Easy | Needs $elemMatch | Easy |
| Unpredictable attributes | Yes | Yes | Yes |
| Type/unit management | Needs registry | Needs registry | Needs registry |
| Indexing frequently used fields | Easy to create dedicated indexes | Multikey has limitations | Easy for core fields |
| Dynamic facets by key | Can use $objectToArray | $unwind is convenient | Depends on design |
| Storage overhead from repeated keys | Relatively low | Higher | Depends |
| Mismatches across array elements | Rare with scalar fields | High if $elemMatch is forgotten | Depends on structure |

There is no single answer for every catalog. A system with a few stable product types does not need a complex key–value array; a marketplace with many verticals may need a strong registry and a more flexible model.

## 9. Attribute Definitions: Per-Category Attribute Dictionary

MongoDB does not inherently know that **ramGB** is in GB, **screenInch** is a positive number, or **color** only accepts standard codes. You should create a metadata registry, for example an **attributeDefinitions** collection:

~~~javascript
db.attributeDefinitions.insertMany([
  {
    _id: "laptops.ramGB",
    categoryId: "laptops",
    key: "ramGB",
    valueType: "number",
    unit: "GB",
    filterKind: "range",
    minAllowed: 4,
    maxAllowed: 256,
    visible: true,
    filterable: true
  },
  {
    _id: "laptops.storageGB",
    categoryId: "laptops",
    key: "storageGB",
    valueType: "number",
    unit: "GB",
    filterKind: "multi-select",
    allowedValues: [256, 512, 1024, 2048],
    visible: true,
    filterable: true
  },
  {
    _id: "laptops.color",
    categoryId: "laptops",
    key: "color",
    valueType: "string",
    filterKind: "multi-select",
    allowedValues: ["black", "gray", "silver"],
    visible: true,
    filterable: true
  },
  {
    _id: "shoes.material",
    categoryId: "shoes",
    key: "material",
    valueType: "string",
    filterKind: "multi-select",
    allowedValues: ["mesh", "leather", "synthetic"],
    visible: true,
    filterable: true
  }
]);
~~~

This registry is an **application model**, not automatically a MongoDB validator. You need ingestion logic, normalization, and optionally **$jsonSchema** for stable constraints.

### 9.1. Useful Metadata

| Registry property | Why it is needed |
|---|---|
| categoryId + key | Key is meaningful within the category scope |
| valueType | Avoid mixing String and Number |
| unit | Standardize ranges and display |
| filterKind | exact, multi-select, numeric range, boolean |
| allowedValues | Block invalid values and build UI |
| filterable | Not every spec needs to be queried |
| visible | Some metadata must not be public |
| multiValued | Whether it holds one or multiple values |
| displayLabelByLocale | Localized display |
| order, group | Facet order and grouping on UI |
| deprecated | Prevent new writers from using old keys |

### 9.2. Do Not Change Keys Based on UI Language

~~~text
Canonical key: ramGB
Vietnamese label: Dung lượng RAM
English label: Memory capacity
~~~

Seller inputs like “RAM”, “Bộ nhớ RAM”, or “Memory” should be mapped to **ramGB** when they truly share the same semantics. Do not store three keys and expect a query on one key to return all products.

### 9.3. Unit Normalization

For example, two suppliers enter:

~~~text
SSD: 512 GB
SSD: 0.5 TB
~~~

If filtering uses storageGB, there must be a consistent rule between **decimal GB/TB** and **binary GiB/TiB**. Do not round arbitrarily because a value might shift across a filter threshold.

Other fields also need standards:

- Weight can be stored as integer grams.
- Dimensions can be stored in millimeters.
- Prices stored as integer minor units or Decimal128.
- Timestamps stored as BSON Date/Instant, resolving timezone on display.
- Enums stored as canonical codes, not translated labels.

### 9.4. Missing, Null, Unknown, and Not Applicable

Shoes do not have a battery, while a phone has a battery whose capacity may be unknown:

~~~text
missing          = field not stored
null             = field present, value null
unknown          = attribute applies, value not yet known
not applicable   = irrelevant to the category
~~~

Do not store **batteryMAh: 0** for shoes and interpret it as zero battery capacity. Choose a schema with consistent semantics and queries.

### 9.5. Preventing Duplicates in the Attribute Pattern

Example of bad data:

~~~javascript
{
  attributes: [
    { key: "ramGB", valueNum: 8 },
    { key: "ramGB", valueNum: 32 }
  ]
}
~~~

If RAM is single-valued, two entries with the same key cause a `>=16` filter to match even though the actual value is ambiguous. Validation is needed during ingestion and updates. Do not assume a unique multikey index on **attributes.key** will catch every case of repeated elements within the same document; a unique multikey index does not enforce uniqueness across elements of a single document the way many expect.

## 10. Category Hierarchy and Inherited Filters

A taxonomy might look like:

~~~text
Electronics
  +-- Computers
      +-- Laptops
      +-- Desktops
  +-- Phones
Fashion
  +-- Shoes
      +-- Running shoes
~~~

The product stores the leaf categoryId, while the categories collection manages ancestry:

~~~javascript
{
  _id: "laptops",
  parentId: "computers",
  ancestorIds: ["electronics", "computers"],
  slug: "laptops",
  enabled: true
}
~~~

### 10.1. Filtering Parent Categories as Well

If the product materializes **categoryAncestorIds**:

~~~javascript
{
  _id: "L-101",
  categoryId: "laptops",
  categoryAncestorIds: ["electronics", "computers"]
}
~~~

then finding products under Electronics is:

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  status: "ACTIVE",
  visibility: "PUBLIC",
  categoryAncestorIds: "electronics"
});
~~~

This reduces the need for recursive queries per request, in exchange for updating product search documents when the taxonomy changes.

### 10.2. Inherited Facet Definitions

~~~text
Electronics: brand, price
Computers: processorFamily
Laptops: ramGB, storageGB, screenInch
~~~

Facets for laptops can be merged from ancestors and the leaf according to an override policy. You must define which keys are inherited and the impact when moving a parent category.

### 10.3. One Collection per Category Is Not Necessary

A marketplace with thousands of categories creating separate collections for all of them will suffer complexity in indexing, code, reporting, and deployment. A shared collection with **categoryId** and polymorphic attributes is usually easier to operate, splitting only when there are genuinely distinct workloads, retention, security, or lifecycles.

## 11. Designing the Filter Contract for APIs

The API should accept **typed and pre-defined parameters**, not raw MongoDB queries:

~~~text
GET /catalog/search
  ?category=laptops
  &brand=acer
  &minRamGB=16
  &maxPriceVnd=30000000
  &sort=price_asc
  &limit=24
~~~

### 11.1. Normalizing into FilterSpec

~~~javascript
{
  scope: {
    tenantId: "SHOP-A",
    status: "ACTIVE",
    visibility: "PUBLIC"
  },
  categoryId: "laptops",
  brandIds: ["acer"],
  numeric: { ramGB: { min: 16 } },
  priceVnd: { max: 30000000 },
  sort: "price_asc",
  limit: 24
}
~~~

**tenantId** is obtained by the backend from authentication, not by blindly trusting a self-declared client value.

### 11.2. AND Between Facets, OR Within the Same Facet

~~~text
brand in [acer, dell]
AND ramGB >= 16
AND storageGB in [512, 1024]
AND price <= 30000000
~~~

MongoDB:

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  categoryId: "laptops",
  status: "ACTIVE",
  visibility: "PUBLIC",
  brandId: { $in: ["acer", "dell"] },
  "attributes.ramGB": { $gte: 16 },
  "attributes.storageGB": { $in: [512, 1024] },
  priceVnd: { $lte: NumberLong("30000000") }
});
~~~

With the sample dataset, the query returns **L-101**.

### 11.3. Parsing and Validating Data

An HTTP query string **"16"** is a String. The backend must parse it into a number and validate:

~~~text
?minRamGB=16   -> integer 16
?minRamGB=abc  -> validation error
?minRamGB=-100 -> validation error
~~~

Do not pass the String “16” into MongoDB and expect numeric comparisons to work properly. Prices should use long/Decimal128 depending on currency and accounting conventions, avoiding Double when monetary precision is required.

### 11.4. Scalar Range and Array Range Differ

With scalar attributes.ramGB:

~~~javascript
db.products.find({
  "attributes.ramGB": { $gte: 8, $lte: 16 }
});
~~~

represents the range [8,16]. If the field is a multi-valued array, the two range conditions could be satisfied by two different elements; use **$elemMatch** when requiring a single element to satisfy both.

### 11.5. Semantics to Align On

- Color and size must match the **same SKU** if purchasing a specific combination.
- Features might mean “has all” ($all), rather than “has at least one” ($in).
- Price must distinguish between list price and final price by channel/discount.
- Availability must specify whether it is system-wide or per specific location.
- Parent categories may include all descendants.

## 12. Safe Filter Processor

An application-layer pipeline:

~~~text
HTTP request
    |
    v
Parse + validate input
    |
    v
Load category attribute definitions
    |
    v
Normalize values / types / units
    |
    v
Resolve tenant and catalog scope from authentication
    |
    v
Build MongoDB query from allowlisted fields
    |
    v
Query + sort + pagination + aggregation facets
    |
    v
Map listing DTO / facet DTO
    |
    v
HTTP response
~~~

### 12.1. Do Not Accept Arbitrary MongoDB Operators

Unsafe:

~~~javascript
// Do not use for public APIs.
const filter = JSON.parse(userSuppliedJson);
db.products.find(filter);
~~~

Users could supply structures extending beyond allowed filters. Instead, the backend accepts structured conditions like:

~~~javascript
{ attribute: "ramGB", comparison: "gte", value: 16 }
~~~

then checks that the key exists in the registry, has type number, uses a valid comparison, has a value within range, and respects a limit on total conditions. Only then does it build the **Bson filter**.

### 12.2. Limiting Complexity

A request could send 1,000 brands, 100 nested conditions, and a limit of one million. Even valid BSON can still cause overload.

You should bound the number of filters, values per facet, page size, category depth, payload size, and aggregation execution time per SLOs.

### 12.3. Normalization for Strings and Text Search

A stable brand ID **acer** is better than display strings like “Acer Inc.” or “ACER”. Title text search, accent/case-insensitive search, and autocomplete have distinct requirements; do not assume a regex containing a user pattern on title will be well-indexed:

~~~javascript
// Avoid passing arbitrary userText directly into a large regex.
{ title: { $regex: userText, $options: "i" } }
~~~

You must control regex metacharacters, length, and index support; consider dedicated Search/autocomplete indexes depending on the product and deployment.

## 13. Product and Variant/SKU Are Two Data Levels

A **Puma Runner** shoe might have:

~~~text
Puma Runner (product)
    |
    +-- black / size 40 / SKU-PUMA-BLK-40 / inStock
    +-- black / size 41 / SKU-PUMA-BLK-41 / outOfStock
    +-- white / size 41 / SKU-PUMA-WHT-41 / inStock
~~~

If you store the product with:

~~~javascript
{
  colors: ["black", "white"],
  sizesEU: [40, 41],
  inStock: true
}
~~~

then the question **“is black size 41 in stock?”** cannot be answered accurately from those three independent values alone. Black may only have size 40 left, while size 41 may only be in stock in White.

### 13.1. Embedding Variants in the Product

~~~javascript
{
  _id: "S-101",
  categoryId: "shoes",
  brandId: "puma",
  variants: [
    {
      sku: "PUMA-BLK-40",
      color: "black",
      sizeEU: 40,
      availableQty: 3
    },
    {
      sku: "PUMA-BLK-41",
      color: "black",
      sizeEU: 41,
      availableQty: 0
    },
    {
      sku: "PUMA-WHT-41",
      color: "white",
      sizeEU: 41,
      availableQty: 4
    }
  ]
}
~~~

To filter on the **same variant**:

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  categoryId: "shoes",
  variants: {
    $elemMatch: {
      color: "black",
      sizeEU: 41,
      availableQty: { $gt: 0 }
    }
  }
});
~~~

The result **does not match S-101** because black/size41 is out of stock.

### 13.2. Wrong Query Without $elemMatch

~~~javascript
db.products.find({
  "variants.color": "black",
  "variants.sizeEU": 41,
  "variants.availableQty": { $gt: 0 }
});
~~~

This can match S-101 based on three different elements. **$elemMatch** is necessary when predicates must be satisfied within the **same array element**.

### 13.3. When to Split SKUs into a Separate Collection?

Embedding works well when:

- The number of variants is small and bounded.
- The detail page usually reads most variants.
- Concurrent updates are rare.
- Documents do not grow unboundedly.

Splitting **productVariants** works well when:

- The number of SKUs is large or continuously growing.
- Prices/inventory update frequently.
- Multiple warehouses/sellers update concurrently.
- Separate indexing/filtering and lifecycles are needed.
- You want to reduce update contention on large product documents.

~~~javascript
{
  _id: "SKU-PUMA-BLK-40",
  tenantId: "SHOP-A",
  productId: "S-101",
  color: "black",
  sizeEU: 40,
  availableQty: 3,
  active: true
}
~~~

With a separate model, you can find **productIds** that have matching SKUs:

~~~javascript
db.productVariants.distinct("productId", {
  tenantId: "SHOP-A",
  active: true,
  color: "black",
  sizeEU: 40,
  availableQty: { $gt: 0 }
});
~~~

In a large catalog, avoid fetching a massive list of productIds and passing them to an unbounded **$in**; you may need a materialized search projection, an indexed $lookup aggregation, or a SKU-centric search architecture.

### 13.4. Inventory Is Not Just a Boolean

A SKU may have:

~~~text
onHand = 10
reserved = 4
damaged = 1
availableToSell = 5
~~~

availableToSell may be a computed number or snapshot rather than a source field. For an inStock filter, you must determine the warehouse/location scope and the authoritative data source.

Listings serve the browsing experience; **checkout must re-verify price/inventory and perform concurrency control**, rather than treating a cached listing as a stock reservation guarantee.

### 13.5. Variant Snapshot/Search Projection

A model might materialize:

~~~javascript
{
  _id: "S-101",
  searchableColors: ["black", "white"],
  searchableSizesEU: [40, 41],
  hasAvailableVariant: true
}
~~~

These summary fields are useful for product-level facet counts, but **cannot prove** that a color+size combination has a real SKU, let alone that the SKU is in stock. You need a variant-pair mapping design:

~~~javascript
{
  availableVariantOptions: [
    { color: "black", sizeEU: 40 },
    { color: "white", sizeEU: 41 }
  ]
}
~~~

Then use **$elemMatch**. Summary/materialized search fields must be updated when inventory changes; synchronization lag must be measured and eventual consistency clearly documented if applicable.

### 13.6. Product Count vs. SKU Count

For example, a shoe product has three SKUs. A size 41 filter can:

- Count **one product** if at least one size 41 SKU matches.
- Count **two SKUs** if there are two size 41 SKUs in different colors.
- Count **one in-stock SKU** if only one size 41 is available.

The UI must declare the **facet count unit**; the aggregation must $group by productId if outputting product-level counts.

## 14. Price and Offers: Separating Highly Volatile Data

A product may be sold across multiple channels:

~~~text
Base product: Laptop A
    |
    +-- Seller A, VND, 22,000,000
    +-- Seller B, VND, 22,500,000
    +-- Seller C, USD, 900.00
~~~

Storing a single **priceVnd** field on the product is only suitable when it is the canonical price of **one catalog and one currency**. Multi-seller/multi-currency marketplaces usually need a separate offers/pricing model:

~~~javascript
{
  _id: "OFFER-101",
  tenantId: "SHOP-A",
  productId: "L-101",
  skuId: "SKU-L-101-A",
  currency: "VND",
  priceMinor: NumberLong("22000000"),
  active: true,
  channel: "web"
}
~~~

**priceMinor** in VND requires a consistent convention for the smallest unit used by the application; for other currencies, scale must be handled according to currency standards rather than assuming all units have two decimal places.

### 14.1. Defining Price Filters

Before using **minPrice/maxPrice**, answer:

- Is it before or after promo codes?
- Is it the cheapest SKU's price or the main product's?
- Which seller's price?
- Which currency and exchange rate at what time?
- Does it include taxes/shipping fees?

**Do not add/mix prices of different currencies** into the same numeric range without converting under a clear policy.

### 14.2. When to Materialize Price on the Product?

For fast listings, you can store:

~~~javascript
{
  minActivePriceVnd: NumberLong("22000000"),
  maxActivePriceVnd: NumberLong("22500000"),
  priceUpdatedAt: ISODate("2026-10-01T00:00:00Z")
}
~~~

This is a **read model** that can become stale when offers change. Checkout still needs to compute and lock the price in the order workflow; the search document is not an accounting system.

## 15. Indexing Strategy for Catalog Queries

A catalog has hundreds of attributes, yet each query only uses a few fields. **Do not create a super-long compound index for every field**; the indexing strategy should stem from real query patterns.

### 15.1. Index for Common Listings

Suppose most queries are:

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  categoryId: "laptops",
  status: "ACTIVE",
  visibility: "PUBLIC"
}).sort({ priceVnd: 1, _id: 1 }).limit(24);
~~~

A reference index:

~~~javascript
db.products.createIndex(
  {
    tenantId: 1,
    categoryId: 1,
    status: 1,
    visibility: 1,
    priceVnd: 1,
    _id: 1
  },
  { name: "catalog_listing_price_asc" }
);
~~~

Equality fields precede sort/range fields matching this query structure. **_id** acts as a tie-breaker to ensure deterministic ordering when multiple products share the same price.

### 15.2. Queries with Brand Equality

~~~javascript
db.products.createIndex(
  {
    tenantId: 1,
    categoryId: 1,
    status: 1,
    visibility: 1,
    brandId: 1,
    priceVnd: 1,
    _id: 1
  },
  { name: "catalog_brand_price" }
);
~~~

An index containing brandId helps **exact brand + price sort** queries under matching conditions. However, if a query does not filter by brand, having brandId before price in the index can prevent it from serving a global price sort as desired; thus, you cannot replace all listing indexes with a single index that has brand in the middle.

### 15.3. Index for RAM Numeric Range

~~~javascript
db.products.createIndex(
  {
    tenantId: 1,
    categoryId: 1,
    status: 1,
    "attributes.ramGB": 1
  },
  { name: "catalog_laptop_ram" }
);
~~~

If RAM is a stable category-specific field, this index can support filtering by RAM; however, a query combining **RAM range + price sort** will not automatically use a single index to optimize both. A range predicate can make sorting on a subsequent field harder to leverage. Inspect the execution plan instead of guessing.

### 15.4. Do Not Create Every Index Combination

If there are:

~~~text
12 facets
3 sort orders
2 availability modes
5 common query shapes
~~~

creating indexes for every permutation will cause massive write amplification, storage overhead, and index maintenance costs. Start with a few query patterns that have high traffic or large document counts, measure real workloads, and adjust.

### 15.5. Indexes for the Attribute Pattern

With the **attributes: [{key, valueNum, valueStr}]** array:

~~~javascript
db.products.createIndex(
  {
    tenantId: 1,
    categoryId: 1,
    "attributes.key": 1,
    "attributes.valueNum": 1
  },
  { name: "attr_numeric_key_value" }
);
~~~

And similarly for String:

~~~javascript
db.products.createIndex(
  {
    tenantId: 1,
    categoryId: 1,
    "attributes.key": 1,
    "attributes.valueStr": 1
  },
  { name: "attr_string_key_value" }
);
~~~

Both paths **attributes.key** and **attributes.valueNum** reside in the same array of documents, so queries using **$elemMatch** enforce that both key and value match within the same element while potentially enabling tighter index bounds for that structure.

**Do not assume** such an index will be fast for an AND query across five different attributes. MongoDB has limitations when combining multiple array paths and may need index scans/intersections, fetch/filter stages, or another plan. Measure executionStats for multi-attribute queries.

### 15.6. Compound Multikey Restrictions

In MongoDB, a single compound multikey index cannot contain **multiple independent array fields** for the same document. An index on **colors** and **sizesEU**, if both are arrays, can violate the parallel arrays restriction; even if built on the current dataset, future writes can make it invalid.

The right design is:

- Use a **single variants array** containing the attribute pairs that must stay bound together.
- Use **$elemMatch** on that array.
- Check the compound multikey rules for your MongoDB version.
- Do not assume splitting color/size into two arrays and compound-indexing them will resolve the relationship between them.

### 15.7. Indexes for the Variants Collection

When SKUs are stored separately and queries start from size/color:

~~~javascript
db.productVariants.createIndex(
  {
    tenantId: 1,
    active: 1,
    color: 1,
    sizeEU: 1,
    productId: 1
  },
  { name: "variant_color_size_product" }
);
~~~

If queries frequently start from productId to display all SKUs:

~~~javascript
db.productVariants.createIndex(
  {
    tenantId: 1,
    productId: 1
  },
  { name: "variant_by_product" }
);
~~~

Two different query patterns may require two indexes. You also need **unique SKU identity** and proper uniqueness rules per seller/tenant, not just relying on an arbitrary SKU string name.

## 16. Wildcard Indexes: When Field Names Vary

For dynamic attribute objects, MongoDB provides a **wildcard index** to index multiple subpaths:

~~~javascript
db.products.createIndex(
  { "attributes.$**": 1 },
  { name: "attributes_wildcard" }
);
~~~

The query might be:

~~~javascript
db.products.find({
  "attributes.batteryMAh": { $gte: 4500 }
});
~~~

Wildcard indexes are useful when all attribute names are unknown at index creation time, but they are **not a magic index**:

- They do not replace compound indexes optimized for frequent equality/category/price sort filters.
- Effectiveness depends on BSON structure, value types, and query shapes.
- They have limitations for sorting, covered queries, and certain predicate combinations.
- For arrays/nested structures, check specific wildcard/multikey rules.
- The index can grow very large when thousands of keys/values are indexed together.

### 16.1. When to Consider Wildcard?

Appropriate when:

- The catalog has many unpredictable new attributes.
- Queries on certain dynamic paths occur at moderate frequency.
- Creating a separate index for every path is impractical.
- Workload and storage overhead have been tested.

Not suitable as a default to optimize:

~~~text
category + brand + RAM + SSD + price sort
~~~

under all conditions. For high-traffic top facets, dedicated indexes are usually more predictable.

### 16.2. Index Selection Process

1. List top query shapes by traffic and cost.
2. Choose specific indexes for stable fields.
3. Evaluate wildcard for rare attributes if needed.
4. Check index size and write amplification.
5. Use explain("executionStats") to compare keys/docs examined and latency.
6. Observe behavior when dataset/index/data skew changes.

## 17. Partial Indexes and Visible Data

A catalog has many ARCHIVED/PRIVATE products, whereas listings only search for ACTIVE/PUBLIC ones. You can consider a partial index:

~~~javascript
db.products.createIndex(
  {
    tenantId: 1,
    categoryId: 1,
    priceVnd: 1,
    _id: 1
  },
  {
    name: "public_active_price",
    partialFilterExpression: {
      status: "ACTIVE",
      visibility: "PUBLIC"
    }
  }
);
~~~

Query conditions must be compatible with the **partialFilterExpression** for the planner to properly use the index. Admin queries viewing ARCHIVED/PRIVATE items cannot use this partial index by default.

### 17.1. A Partial Index Is Not Authorization

If an application forgets the visibility or tenantId filter, **a partial index will not block** it from reading private data; an index is a performance and limited constraint tool, not a substitute for authorization.

### 17.2. TTL Is Not a Discontinued Status

Do not use TTL to auto-delete products simply because they are out of stock or temporarily discontinued. TTL actually deletes documents once they become eligible under the TTL index. Catalogs typically need to preserve product history, order references, and audit trails; use status/visibility and an appropriate retention policy instead.

## 18. Reading Execution Plans to Know If an Index Helps

Example:

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  categoryId: "laptops",
  status: "ACTIVE",
  visibility: "PUBLIC",
  brandId: "acer",
  "attributes.ramGB": { $gte: 16 },
  priceVnd: { $lte: NumberLong("30000000") }
}).sort({ priceVnd: 1, _id: 1 })
  .explain("executionStats");
~~~

Observe:

| Indicator | Meaning |
|---|---|
| **winningPlan** | The chosen execution plan |
| **IXSCAN** | An index scan is used |
| **COLLSCAN** | Collection scan |
| **FETCH** | Needs to load documents to check/return fields |
| **SORT** | There may be an in-memory sort step not satisfied by an index |
| **totalKeysExamined** | Number of index entries examined |
| **totalDocsExamined** | Number of documents read/checked |
| **nReturned** | Number of documents returned |
| **executionTimeMillis** | Reference execution time metric |

**An IXSCAN does not automatically mean a fast query.** If it scans millions of keys to return 24 products, check selectivity and index order. Conversely, with eight test records, COLLSCAN can be faster than IXSCAN and does not prove a production index is useless.

### 18.1. Choosing Representative Benchmark Data

In production, it is possible that:

- 70% of products belong to 3 popular brands.
- 90% of products are ACTIVE.
- One category holds 80% of all records.
- One facet such as color=black is extremely common.

An index well-suited for a rare brand is not necessarily optimal for a very popular brand. Benchmarks should represent real distributions while measuring p50/p95/p99 latency, CPU/IO, query execution, and index maintenance.

## 19. Faceted Search: Dynamic Filters with Counts

A catalog page typically displays:

~~~text
Category: Laptop
Brand
  [ ] Acer (2)
  [ ] Dell (1)
  [ ] Lenovo (1)

RAM
  [ ] 8 GB (1)
  [ ] 16 GB (2)
  [ ] 32 GB (1)

Price range
  [ ] Under 20 million
  [ ] 20–30 million
  [ ] Over 30 million
~~~

**Facet count** is the number of products in a defined set, not necessarily the total number of documents in the entire collection.

### 19.1. Basic Facets for a Category

Counting by brand, only for products in SHOP-A, laptops, and currently visible:

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      categoryId: "laptops",
      status: "ACTIVE",
      visibility: "PUBLIC"
    }
  },
  {
    $group: {
      _id: "$brandId",
      productCount: { $sum: 1 }
    }
  },
  { $sort: { productCount: -1, _id: 1 } }
]);
~~~

With the sample data:

| Brand | Product count |
|---|---:|
| acer | 2 |
| dell | 1 |
| lenovo | 1 |

If **tenantId** is forgotten, Acer increases from 2 to 3 due to SHOP-B's product. If DRAFT/ARCHIVED statuses are also counted, the counts may violate business rules as well.

### 19.2. Facet for a Numeric Attribute

Counting RAM values in the laptops category:

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      categoryId: "laptops",
      status: "ACTIVE",
      visibility: "PUBLIC",
      "attributes.ramGB": { $type: "number" }
    }
  },
  {
    $group: {
      _id: "$attributes.ramGB",
      productCount: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Result:

~~~javascript
[
  { _id: 8, productCount: 1 },
  { _id: 16, productCount: 2 },
  { _id: 32, productCount: 1 }
]
~~~

### 19.3. Range Facet with $bucket

Splitting prices into defined thresholds:

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      categoryId: "laptops",
      status: "ACTIVE",
      visibility: "PUBLIC"
    }
  },
  {
    $bucket: {
      groupBy: "$priceVnd",
      boundaries: [
        NumberLong("0"),
        NumberLong("20000000"),
        NumberLong("30000000"),
        NumberLong("50000000")
      ],
      default: "OTHER",
      output: {
        productCount: { $sum: 1 }
      }
    }
  }
]);
~~~

MongoDB **$bucket** uses an inclusive lower bound and an exclusive upper bound for boundaries; with the sample values:

| Price | Products | Count |
|---|---|---:|
| [0, 20 million) | L-102 | 1 |
| [20, 30 million) | L-101 | 1 |
| [30, 50 million) | L-103, L-104 | 2 |

If the UI says “20 million or less” while $bucket uses [0, 20 million), the contract is misaligned at the boundary. Labels and queries must match in inclusivity.

### 19.4. Counting a Product or a Variant?

A product document may have multiple variants of the same color or size. If you unwind variants and group by color, each variant can inflate the count; if the UI wants **product count**, you must deduplicate **product ID + facet value** before counting.

Example with embedded variants:

~~~javascript
db.products.aggregate([
  { $match: { tenantId: "SHOP-A", categoryId: "shoes" } },
  { $unwind: "$variants" },
  { $match: { "variants.availableQty": { $gt: 0 } } },
  {
    $group: {
      _id: {
        productId: "$_id",
        color: "$variants.color"
      }
    }
  },
  {
    $group: {
      _id: "$_id.color",
      productCount: { $sum: 1 }
    }
  }
]);
~~~

The first group stage deduplicates variants of **the same product and same color**, and the second stage counts the number of products per color.

## 20. Facet Counts After the User Selects Filters

Suppose the user selects:

~~~text
brand = acer
ramGB >= 16
~~~

In the sample, the current results are **L-101** and **L-104**, total=2.

There are two count models:

1. **Conjunctive counts:** computed over the set with all filters applied, so other brands do not appear if Acer is already selected.
2. **Self-excluding / disjunctive counts:** when computing the Brand facet, omit the Brand filter while keeping RAM; when computing the RAM facet, omit RAM while keeping Brand. The UI sees available alternative choices.

No single semantics fits every product; a consistent policy must be chosen.

### 20.1. Conjunctive Counts

If all conditions are applied:

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      categoryId: "laptops",
      status: "ACTIVE",
      visibility: "PUBLIC",
      brandId: "acer",
      "attributes.ramGB": { $gte: 16 }
    }
  },
  { $group: { _id: "$brandId", count: { $sum: 1 } } }
]);
~~~

only **acer: 2** appears. Dell/Lenovo options will have no counts because brand was filtered.

### 20.2. Self-Excluding Counts

When computing Brand, **omit the Brand condition** while keeping RAM≥16:

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      categoryId: "laptops",
      status: "ACTIVE",
      visibility: "PUBLIC",
      "attributes.ramGB": { $gte: 16 }
    }
  },
  { $group: { _id: "$brandId", count: { $sum: 1 } } },
  { $sort: { count: -1, _id: 1 } }
]);
~~~

Result:

~~~javascript
[
  { _id: "acer", count: 2 },
  { _id: "dell", count: 1 }
]
~~~

Lenovo has 8 GB RAM so it does not appear. Users still see Dell as a relevant option if they clear or switch the brand filter.

Conversely, when computing RAM, keep brand=acer while **omitting the RAM condition**:

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      categoryId: "laptops",
      status: "ACTIVE",
      visibility: "PUBLIC",
      brandId: "acer"
    }
  },
  {
    $group: {
      _id: "$attributes.ramGB",
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Result: **RAM 16: 1, RAM 32: 1**.

### 20.3. Multiple Values in the Same Facet

If the user selects **brand=acer,dell**, OR semantics within Brand should allow:

~~~javascript
brandId: { $in: ["acer", "dell"] }
~~~

When computing the Brand facet in self-excluding mode, drop the **entire Brand condition**, not just one value. Other UX patterns (e.g., drill-down facets) may choose a different policy; backend and UI must agree.

### 20.4. Facets Should Not Always Show Every Value

For an attribute like modelNumber with 100,000 values, returning everything makes the JSON huge. You should:

- Show only the top N facet values by count.
- Support searching within facet values if needed.
- Use allowedValues metadata for finite filters.
- Avoid unbounded grouping across all String values.
- Define behavior for selected facet values that currently have count=0.

## 21. $facet: Combining Multiple Results into One Aggregation

**$facet** allows multiple aggregation branches from the same input dataset. One pipeline can return **items**, **total count**, **brand counts**, and **RAM counts** in a single document.

### 21.1. Self-Excluding Example with Two Facets

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      categoryId: "laptops",
      status: "ACTIVE",
      visibility: "PUBLIC"
    }
  },
  {
    $facet: {
      items: [
        {
          $match: {
            brandId: "acer",
            "attributes.ramGB": { $gte: 16 }
          }
        },
        { $sort: { priceVnd: 1, _id: 1 } },
        { $limit: 24 },
        {
          $project: {
            title: 1,
            brandId: 1,
            priceVnd: 1
          }
        }
      ],
      total: [
        {
          $match: {
            brandId: "acer",
            "attributes.ramGB": { $gte: 16 }
          }
        },
        { $count: "value" }
      ],
      brands: [
        { $match: { "attributes.ramGB": { $gte: 16 } } },
        { $group: { _id: "$brandId", count: { $sum: 1 } } },
        { $sort: { count: -1, _id: 1 } }
      ],
      ramValues: [
        { $match: { brandId: "acer" } },
        {
          $group: {
            _id: "$attributes.ramGB",
            count: { $sum: 1 }
          }
        },
        { $sort: { _id: 1 } }
      ]
    }
  }
]);
~~~

Output structure:

~~~javascript
{
  items: [ /* L-101, L-104 */ ],
  total: [ { value: 2 } ],
  brands: [
    { _id: "acer", count: 2 },
    { _id: "dell", count: 1 }
  ],
  ramValues: [
    { _id: 16, count: 1 },
    { _id: 32, count: 1 }
  ]
}
~~~

Note that **total is an array**, which can be empty if $count receives no input. The API mapper should return total=0 per the contract when the array is empty, rather than unconditionally accessing element [0].

### 21.2. Why Put the Common $match Before $facet?

**tenantId, status, visibility, and category** apply to **every branch**, so placing a common $match at the start:

- Guarantees proper scoping.
- Has the opportunity to leverage an index at the start of the pipeline.
- Reduces the number of documents entering the facet branches.

If $facet is the first stage of the pipeline, it generally cannot leverage an index to narrow the input set the way a preceding $match can.

### 21.3. $facet Is Not Free

- Each branch processes the input document set.
- A top-level facet result contains multiple arrays and is subject to the BSON document size limit.
- The $facet stage has its own memory limit; **allowDiskUse** does not overcome all such limits.
- Sorting/grouping across many branches can consume significant CPU/memory.
- A pipeline with 40 facet branches is not automatically faster than 40 individual queries.

For very large catalogs, you can split into **items query**, **facet queries**, and **materialized facet counts** with a clear caching/refresh policy.

## 22. Dynamic Facets When Keys Are Unknown in Advance

With an attributes object, MongoDB can convert the object into an array using **$objectToArray** to group by key name:

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      categoryId: "laptops",
      status: "ACTIVE",
      visibility: "PUBLIC"
    }
  },
  { $project: { entries: { $objectToArray: "$attributes" } } },
  { $unwind: "$entries" },
  {
    $group: {
      _id: {
        key: "$entries.k",
        value: "$entries.v"
      },
      productCount: { $sum: 1 }
    }
  },
  { $sort: { "_id.key": 1, productCount: -1 } }
]);
~~~

Example output:

~~~javascript
{ _id: { key: "ramGB", value: 16 }, productCount: 2 }
{ _id: { key: "ramGB", value: 8 }, productCount: 1 }
{ _id: { key: "color", value: "black" }, productCount: 2 }
~~~

### 22.1. Do Not Expose Every Field as a Facet

The attribute object may contain serialNumber, manufacturingBatch, or internalNotes. Do not automatically expose all key/value pairs after $objectToArray. Only retain keys marked by the registry as **filterable=true, visible=true** and authorized for display. Do not rely solely on the frontend to hide a facet containing sensitive data.

### 22.2. Arrays and Nested Values Need Special Handling

If:

~~~javascript
{ ports: ["USB-C", "HDMI"] }
~~~

$objectToArray produces one entry whose **value is the entire array**; it does not automatically create two port facets. You need to unwind/normalize by value. If a product repeats the same port, deduplicate **product+facet value** before counting.

Nested objects:

~~~javascript
{ dimensions: { widthMm: 300, heightMm: 25 } }
~~~

should not be grouped as a single facet value. Register explicit paths like dimensions.widthMm if filtering is actually needed.

### 22.3. Attribute Pattern Generates Facets via $unwind

With an array of key–value objects:

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      categoryId: "laptops",
      status: "ACTIVE",
      visibility: "PUBLIC"
    }
  },
  { $unwind: "$attributes" },
  { $match: { "attributes.key": { $in: ["color", "ramGB"] } } },
  {
    $group: {
      _id: {
        key: "$attributes.key",
        stringValue: "$attributes.valueStr",
        numberValue: "$attributes.valueNum"
      },
      count: { $sum: 1 }
    }
  }
]);
~~~

This is an illustrative pattern. With differently typed data, separate numeric/string branches or build a canonical group key representation; missing fields can create a null group. Validate against accidental duplicate keys.

### 22.4. Sum of Facet Counts Can Exceed Total Products

If a product has two colors, it may contribute 1 to black and 1 to white. Having the sum of all color counts exceed total products is not necessarily wrong. However, one product must not be counted twice toward **the same color value** if the UI counts products.

## 23. Pagination and Stable Sorting

### 23.1. Offset Pagination

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  categoryId: "laptops",
  status: "ACTIVE",
  visibility: "PUBLIC"
}).sort({ priceVnd: 1, _id: 1 })
  .skip(24)
  .limit(24);
~~~

Advantage: simple. Limitation: large skips waste work discarding rows; data changes between pages can cause duplicates or skipped items.

### 23.2. Adding _id as a Tie-Breaker

Sorting only by price:

~~~javascript
{ priceVnd: 1 }
~~~

does not guarantee a deterministic order among products with the same price. Use:

~~~javascript
{ priceVnd: 1, _id: 1 }
~~~

to obtain a deterministic order over the observed data state.

### 23.3. Keyset Pagination

With ascending sort **(priceVnd, _id)** and the cursor of the last item:

~~~javascript
{ lastPriceVnd: NumberLong("22000000"), lastId: "L-101" }
~~~

the next page is:

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  categoryId: "laptops",
  status: "ACTIVE",
  visibility: "PUBLIC",
  $or: [
    { priceVnd: { $gt: NumberLong("22000000") } },
    {
      priceVnd: NumberLong("22000000"),
      _id: { $gt: "L-101" }
    }
  ]
}).sort({ priceVnd: 1, _id: 1 })
  .limit(24);
~~~

The backend must bind the cursor to the tenant/filter/sort to prevent clients from tampering with scope. The cursor can be signed or encoded with a filter hash and version.

### 23.4. Keyset Does Not Create an Immutable Snapshot

If prices change between two pages, products can shift positions. Keyset pagination does not automatically guarantee snapshot isolation for an entire browsing session; stronger requirements need a snapshot or search versioning design.

### 23.5. Total and Facet Counts Must Cover the Entire Result Set

**Counts are usually calculated over the full matching set**, not just the 24-product page. If facets are computed after $skip/$limit, the UI only sees counts for a single page.

~~~text
authenticated scope + filters
              |
         +----+----+
         |         |
         v         v
     items page  facet counts
     sort/limit  over full match set
~~~

An exact total count can be expensive. If the UI accepts **hasMore** or cached/estimated counts, clearly document the semantics instead of presenting an unverified number as exact.

## 24. Projection and Payload Size

Listings should return only needed fields like _id/title/brand/price/thumbnail, rather than returning all of:

~~~text
longDescription
technicalSpecs
allImages
supplierInternalCost
allVariants
moderationHistory
~~~

~~~javascript
db.products.find(
  {
    tenantId: "SHOP-A",
    categoryId: "laptops",
    status: "ACTIVE",
    visibility: "PUBLIC"
  },
  {
    title: 1,
    brandId: 1,
    priceVnd: 1,
    thumbnailUrl: 1
  }
).sort({ priceVnd: 1, _id: 1 }).limit(24);
~~~

Projection reduces payload size and can reduce I/O; it does not replace authorization. The backend must not return supplierCost or private metadata simply because they live in the same document.

### 24.1. Denormalization for Listings

Brand labels/thumbnailUrl can be copied into the search document to avoid joins, but this creates synchronization responsibilities when brand names, images, or locales change. Only denormalize fields with clear benefits and an update process; do not copy all related data blindly.

## 25. Java MongoDB Sync Driver: Building Safe Filters

A Java service typically receives filter options after the controller has parsed and validated them. Do not let the repository accept a raw JSON query or an unvalidated field path.

### 25.1. Filter Specification

~~~java
import java.util.List;

public record CatalogFilter(
        String categoryId,
        List<String> brandIds,
        Integer minRamGB,
        Long maxPriceVnd,
        int limit
) {
}
~~~

**tenantId is not in CatalogFilter** because this scope should be resolved by the service from the authenticated identity, preventing requests from spoofing a tenant.

### 25.2. Repository Using Filters/Sorts/Projections

~~~java
import java.util.ArrayList;
import java.util.List;

import com.mongodb.client.FindIterable;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

public final class ProductSearchRepository {
    private final MongoCollection<Document> products;

    public ProductSearchRepository(
            MongoCollection<Document> products) {
        this.products = products;
    }

    public List<Document> findProducts(
            String trustedTenantId,
            CatalogFilter requested) {

        if (trustedTenantId == null || trustedTenantId.isBlank()) {
            throw new IllegalArgumentException(
                    "Authenticated tenant is required");
        }
        if (requested.categoryId() == null ||
                requested.categoryId().isBlank()) {
            throw new IllegalArgumentException("Category is required");
        }
        if (requested.limit() < 1 || requested.limit() > 48) {
            throw new IllegalArgumentException(
                    "Page size must be 1..48");
        }
        if (requested.maxPriceVnd() != null &&
                requested.maxPriceVnd() < 0) {
            throw new IllegalArgumentException("Invalid price");
        }
        if (requested.minRamGB() != null &&
                (requested.minRamGB() < 1 ||
                 requested.minRamGB() > 256)) {
            throw new IllegalArgumentException("Invalid RAM filter");
        }

        List<Bson> clauses = new ArrayList<>();
        clauses.add(Filters.eq("tenantId", trustedTenantId));
        clauses.add(Filters.eq("categoryId", requested.categoryId()));
        clauses.add(Filters.eq("status", "ACTIVE"));
        clauses.add(Filters.eq("visibility", "PUBLIC"));

        if (requested.brandIds() != null &&
                !requested.brandIds().isEmpty()) {
            if (requested.brandIds().size() > 20) {
                throw new IllegalArgumentException("Too many brands");
            }
            clauses.add(Filters.in("brandId", requested.brandIds()));
        }
        if (requested.minRamGB() != null) {
            clauses.add(Filters.gte(
                    "attributes.ramGB", requested.minRamGB()));
        }
        if (requested.maxPriceVnd() != null) {
            clauses.add(Filters.lte(
                    "priceVnd", requested.maxPriceVnd()));
        }

        FindIterable<Document> query = products.find(
                Filters.and(clauses))
                .sort(Sorts.orderBy(
                        Sorts.ascending("priceVnd"),
                        Sorts.ascending("_id")))
                .projection(Projections.include(
                        "title", "brandId",
                        "priceVnd", "thumbnailUrl"))
                .limit(requested.limit());

        return query.into(new ArrayList<>());
    }
}
~~~

This is an example for the **object attributes schema** with a bounded result list; a production API still needs to:

- Validate that the category permits filtering by RAM (do not allow applying RAM to shoes).
- Map brand aliases to canonical brandIds.
- Support min/max price together.
- Handle sort allowlisting and pagination cursors.
- Apply timeouts and safe logging/metrics.
- Limit complexity and protect response DTOs.

**Do not create a MongoClient on every findProducts() call**. Inject MongoCollection from a shared MongoClient scoped to the application lifecycle.

### 25.3. Querying the Attribute Pattern with Filters.elemMatch

~~~java
import com.mongodb.client.model.Filters;
import org.bson.conversions.Bson;

Bson ramFilter = Filters.elemMatch(
        "attributes",
        Filters.and(
                Filters.eq("key", "ramGB"),
                Filters.gte("valueNum", 16)
        )
);

Bson storageFilter = Filters.elemMatch(
        "attributes",
        Filters.and(
                Filters.eq("key", "storageGB"),
                Filters.gte("valueNum", 512)
        )
);

Bson combined = Filters.and(
        Filters.eq("tenantId", "SHOP-A"),
        Filters.eq("categoryId", "laptops"),
        ramFilter,
        storageFilter
);
~~~

Two independent **elemMatch** clauses on the same array express **requires a matching ramGB entry** and **requires a matching storageGB entry**. All operators are built by the backend from the registry; arbitrary keys or numeric types are never accepted.

### 25.4. Querying Variants Within the Same Element

~~~java
Bson inStockBlack41 = Filters.elemMatch(
        "variants",
        Filters.and(
                Filters.eq("color", "black"),
                Filters.eq("sizeEU", 41),
                Filters.gt("availableQty", 0)
        )
);
~~~

This checks whether **at least one matching variant exists**; it does not mean all variants of the product are available.

### 25.5. Dynamic Paths Only After Allowlisting

Suppose the registry has validated a key:

~~~java
import java.util.Set;

Set<String> allowedNumericFilters =
        Set.of("ramGB", "storageGB", "screenInch");

String attributeKey = requestedAttributeKey;
if (!allowedNumericFilters.contains(attributeKey)) {
    throw new IllegalArgumentException(
            "Unsupported numeric filter");
}

Bson minFilter = Filters.gte(
        "attributes." + attributeKey, numericMinValue);
~~~

This pattern is only valid when **requestedAttributeKey** has been validated against the category and the numeric value has been properly parsed beforehand. Simply checking that a string starts with "attributes." is not enough to block unwanted field paths.

## 26. Java Driver: Basic Facet Aggregation

The Java Sync Driver provides builders for aggregation stages. Example counting by brand:

~~~java
import java.util.ArrayList;
import java.util.List;

import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Accumulators;
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

public List<Document> countByBrand(
        MongoCollection<Document> products,
        String trustedTenantId) {

    List<Bson> pipeline = List.of(
            Aggregates.match(Filters.and(
                    Filters.eq("tenantId", trustedTenantId),
                    Filters.eq("categoryId", "laptops"),
                    Filters.eq("status", "ACTIVE"),
                    Filters.eq("visibility", "PUBLIC")
            )),
            Aggregates.group(
                    "$brandId",
                    Accumulators.sum("productCount", 1)
            ),
            Aggregates.sort(
                    Sorts.orderBy(
                            Sorts.descending("productCount"),
                            Sorts.ascending("_id")
                    ))
    );

    return products.aggregate(pipeline)
            .into(new ArrayList<>());
}
~~~

This snippet illustrates a method inside a service/repository class. The result Document has **_id** as brandId and **productCount** as an appropriate numeric type. In a real API, map it to a **BrandFacetDto** with consistent field names instead of returning raw BSON responses externally.

### 26.1. Result Counts Can Be Empty

If a category has no products, the group aggregation returns an empty list. The service should return:

~~~javascript
{ facets: [], total: 0 }
~~~

per the contract. Do not assume every facet has items.

### 26.2. Be Careful Materializing Long Lists

**into(new ArrayList<>())** is suitable for a bounded number of facet groups; it should not be used to load millions of products into RAM. For large datasets, use cursors/batching and ensure resources are closed according to the appropriate lifecycle.

## 27. Spring Data MongoDB: Polymorphic Entities

With Spring Boot, you can use **MongoTemplate** and an entity containing core fields along with an attributes map.

~~~java
import java.util.Map;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("products")
public class ProductDocument {
    @Id
    private String id;

    private String tenantId;
    private String categoryId;
    private String brandId;
    private String title;
    private String status;
    private String visibility;
    private long priceVnd;
    private Map<String, Object> attributes;

    public ProductDocument() {
    }

    // Project getters/setters or constructor binding.
}
~~~

### 27.1. Why Map<String,Object> Does Not Solve Everything

A Map allows variable attributes, but:

- Numbers may be converted to Integer/Long/Double depending on the BSON type.
- Null vs. missing values differ.
- The Java compiler does not know ramGB is always numeric.
- When retrieving attributes.get("ramGB"), you must validate the type before casting.
- It does not guarantee a category only contains valid keys.

For complex domains, you can use **typed value objects**, category-specific classes, or custom converters. Map here demonstrates a flexible structure, not a mandatory choice for every project.

### 27.2. Querying with MongoTemplate

~~~java
import java.util.List;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public final class ProductCatalogService {
    private final MongoTemplate mongoTemplate;

    public ProductCatalogService(
            MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<ProductDocument> searchLaptops(
            String trustedTenantId,
            int minRamGB,
            long maxPriceVnd) {

        if (minRamGB < 1 || maxPriceVnd < 0) {
            throw new IllegalArgumentException("Invalid filter");
        }

        Query query = new Query(
                Criteria.where("tenantId").is(trustedTenantId)
                        .and("categoryId").is("laptops")
                        .and("status").is("ACTIVE")
                        .and("visibility").is("PUBLIC")
                        .and("attributes.ramGB").gte(minRamGB)
                        .and("priceVnd").lte(maxPriceVnd)
        );

        query.with(Sort.by(
                Sort.Order.asc("priceVnd"),
                Sort.Order.asc("_id")
        ));
        query.limit(24);

        return mongoTemplate.find(
                query, ProductDocument.class);
    }
}
~~~

In **ProductDocument** above, Java property names match BSON field names. If using **@Field("price_vnd")** or other mappings, use the Spring Data mapping context properly; do not copy untyped BSON queries and expect field names to map identically across all overloads.

### 27.3. Projecting into a DTO Instead of the Full Entity

Suppose you want to avoid loading large attributes:

~~~java
Query query = new Query(
        Criteria.where("tenantId").is(trustedTenantId)
                .and("categoryId").is("laptops")
);

query.fields()
        .include("_id")
        .include("title")
        .include("brandId")
        .include("priceVnd");
~~~

This is a **field projection**. If mapped onto the full **ProductDocument**, unreturned fields will be null/default. The API should use a **listing DTO** or a dedicated mapping instead of treating a partially populated entity as a complete entity that can be saved back.

### 27.4. Querying the Variants Array with Criteria.elemMatch

~~~java
Criteria variantCriteria = Criteria.where("variants")
        .elemMatch(
                Criteria.where("color").is("black")
                        .and("sizeEU").is(41)
                        .and("availableQty").gt(0)
        );

Query query = new Query(
        new Criteria().andOperator(
                Criteria.where("tenantId").is(trustedTenantId),
                Criteria.where("categoryId").is("shoes"),
                variantCriteria
        )
);
~~~

**Criteria.elemMatch** accurately expresses the condition on the same array element, rather than independently having color/size/stock across different elements.

### 27.5. Two Different Attributes in the Attribute Pattern

~~~java
Criteria hasRam = Criteria.where("attributes")
        .elemMatch(
                Criteria.where("key").is("ramGB")
                        .and("valueNum").gte(16)
        );

Criteria hasStorage = Criteria.where("attributes")
        .elemMatch(
                Criteria.where("key").is("storageGB")
                        .and("valueNum").gte(512)
        );

Query query = new Query(
        new Criteria().andOperator(
                Criteria.where("tenantId").is(trustedTenantId),
                Criteria.where("categoryId").is("laptops"),
                hasRam,
                hasStorage
        )
);
~~~

Note: this is a **different schema option** from the ProductDocument Map in section 27. To use the Attribute Pattern in a real entity, declare **List<AttributeValue>** or use MongoTemplate with the collection name/Document matching the model.

## 28. Spring Data Aggregation and Facet DTOs

Spring Data supports the Aggregation API to compute facet counts; for example, counting brands for a category:

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.query.Criteria;

import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;

Aggregation aggregation = newAggregation(
        match(Criteria.where("tenantId").is(trustedTenantId)
                .and("categoryId").is("laptops")
                .and("status").is("ACTIVE")
                .and("visibility").is("PUBLIC")),
        group("brandId").count().as("productCount"),
        project("productCount")
                .and("_id").as("brandId")
                .andExclude("_id")
);

AggregationResults<BrandFacet> results =
        mongoTemplate.aggregate(
                aggregation, "products", BrandFacet.class);

List<BrandFacet> brands = results.getMappedResults();
~~~

DTO:

~~~java
public record BrandFacet(String brandId, long productCount) {
}
~~~

MongoDB **$group** produces an **_id** key; here **$project** transforms _id into brandId to match the record. If you omit project and map into a record with brandId, the field can be null/missing due to the mismatched output shape.

### 28.1. Building Multiple Facet Branches

~~~java
Aggregation agg = newAggregation(
        match(Criteria.where("tenantId").is(trustedTenantId)
                .and("categoryId").is("laptops")
                .and("status").is("ACTIVE")
                .and("visibility").is("PUBLIC")),
        facet(
                group("brandId").count().as("count"),
                project("count")
                        .and("_id").as("brandId")
                        .andExclude("_id")
        ).as("brands")
         .and(
                group("attributes.ramGB").count().as("count"),
                project("count")
                        .and("_id").as("ramGB")
                        .andExclude("_id")
        ).as("ramValues")
);

AggregationResults<org.bson.Document> raw =
        mongoTemplate.aggregate(
                agg, "products", org.bson.Document.class);
~~~

The top-level output is **one document containing two arrays**. To map to a typed DTO:

~~~java
import java.util.List;

public record CatalogFacetResponse(
        List<BrandCount> brands,
        List<RamCount> ramValues
) {}

public record BrandCount(String brandId, long count) {}
public record RamCount(Integer ramGB, long count) {}
~~~

In real Java code, each public top-level record must reside in its own file. If the output has no groups, branches can return empty arrays; defaults in the API response must be decided.

### 28.2. Self-Excluding Facets in Spring Data

The branches in section 21 apply **different filters**. With Spring Data, construct each **AggregationOperation[]** with the exact match conditions for:

- Items: brand + RAM + other filters.
- Brands: RAM + other filters, **without brand**.
- RAM: brand + other filters, **without RAM**.

Do not place a **$match brand+RAM before $facet** and expect the brand branch to un-filter brand later; data removed in an earlier stage cannot be recovered by a branch.

### 28.3. When Is @Aggregation on a Repository Appropriate?

A short, fixed pipeline with a clear output DTO can use Spring Data repository's **@Aggregation**. For dynamic search filters where each facet branch has its own exclusion logic, MongoTemplate or Java Driver Aggregation builders are usually easier to control than concatenating JSON annotation strings.

Never accept raw pipeline JSON from users to execute directly with backend privileges.

## 29. Validation: Flexible Schemas Still Need Constraints

A multi-vertical catalog may not require every product to have **attributes.ramGB**, yet it usually needs every product to have valid core fields.

### 29.1. Validator for Core Fields

Illustrative **$jsonSchema** example:

~~~javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: [
      "tenantId", "categoryId", "title",
      "status", "visibility", "priceVnd"
    ],
    properties: {
      tenantId: { bsonType: "string" },
      categoryId: { bsonType: "string" },
      title: { bsonType: "string" },
      status: {
        enum: ["DRAFT", "ACTIVE", "ARCHIVED"]
      },
      visibility: {
        enum: ["PUBLIC", "PRIVATE"]
      },
      priceVnd: {
        bsonType: "long",
        minimum: 0
      },
      attributes: { bsonType: "object" }
    }
  }
}
~~~

This is a **validator fragment**, not an executed command. On a collection with an existing validator, **collMod** must merge existing constraints; replacing the entire expression can accidentally weaken protections.

### 29.2. Per-Category Rules

Laptops may require:

~~~text
ramGB: positive number
storageGB: positive number
screenInch: positive number
~~~

Shoes have:

~~~text
material: enum
gender: enum
~~~

Do not treat storing everything in a shared collection as an excuse to skip validation. Use app-level registry validation, conditional schema validation, import-time checks, and versioned definitions as needed. Validators alone do not solve every business invariant; app validation does not protect against admin/ETL writers if they write directly.

### 29.3. Updating a Single Attribute

~~~javascript
db.products.updateOne(
  {
    _id: "L-101",
    tenantId: "SHOP-A",
    status: { $ne: "ARCHIVED" }
  },
  {
    $set: {
      "attributes.ramGB": 32,
      updatedAt: new Date()
    }
  }
);
~~~

This is an atomic update of **a single document**. If changing RAM requires updating SKUs, prices, or search projections in another collection, a synchronization workflow is needed; updating one field does not automatically update all copies.

### 29.4. Do Not Let Sellers Send Arbitrary BSON Paths

The attribute ingestion API must map inputs to a **canonical key** from the registry before constructing paths. Never use arbitrary keys as dotted paths, especially keys containing dots, dollar prefixes, or colliding with reserved fields.

### 29.5. Idempotent Imports

Seller feeds may ingest the same product multiple times:

~~~javascript
{
  tenantId: "SHOP-A",
  source: "supplier-7",
  sourceProductId: "P-9001"
}
~~~

Use a stable source identity, conditional upserts, and appropriate unique indexes; do not insert a new document on every feed run. When feeds update concurrently, use a sourceVersion/sequence or optimistic revision so an older source does not overwrite newer information.

## 30. Attribute Evolution and Schema Migration

A catalog may rename **storage** to **storageGB**, or convert **"16 GB"** (String) to 16 (Number). This is a data change, not just a UI label change.

### 30.1. Do Not Change a Field in a Single Release

Old document:

~~~javascript
{ "attributes.storage": "512 GB" }
~~~

New filter:

~~~javascript
{ "attributes.storageGB": 512 }
~~~

Old documents will vanish from results if not migrated first. Roll out via:

~~~text
Expand readers: accept old/new
 -> Update writers: canonical new field
 -> Backfill: parse/convert old data
 -> Reconcile: verify types/counts
 -> Switch filters and indexes
 -> Contract: remove old field and index
~~~

### 30.2. $rename Is Not Enough When Changing Type or Unit

~~~javascript
db.products.updateMany(
  {},
  {
    $rename: {
      "attributes.storage": "attributes.storageGB"
    }
  }
);
~~~

This command only renames the field; **"512 GB"** remains a String. Type parsing/mapping, validation, and a plan for invalid data are needed. Additionally, $rename can overwrite an existing target field, so do not run it blindly on a mixed schema.

### 30.3. Mixed Schemas During Rolling Deployments

- Readers may need to support both keys.
- Writers must establish the canonical field.
- New indexes must be ready before filter cutover.
- Facet counts must not double-count two aliases as two different attributes.
- Backfills must be idempotent and not overwrite newer fields.

### 30.4. Registry Versioning

A new attribute definition does not automatically rewrite data stored under old keys. Deprecation/aliases, data migration, and cross-version API query testing are required.

### 30.5. Large-Scale Backfills

For millions of products, use bounded batches, guarded updates, checkpoints, retries, rate limiting, and replication lag monitoring. Do not use one giant transaction to “migrate the entire collection schema” if an idempotent backfill + reconciliation strategy meets the requirements.

## 31. Text Search and Structured Filtering Are Different Requirements

Users typically have two goals:

1. **Text search:** searching by words/phrases in titles, descriptions, brand aliases.
2. **Structured filtering:** category, price, RAM, color, size, availability.

MongoDB **find + indexes** works well for many structured filters. Full-text relevance, autocomplete, fuzzy search, synonyms, or large search facets may require **MongoDB Search/Atlas Search** or another search service depending on deployment.

### 31.1. $text Is Not Everything

MongoDB text indexes and **$text** have specific capabilities, but do not automatically provide autocomplete, semantic search, or optimal arbitrary substring search. Evaluate language, index, and use case requirements.

### 31.2. Search Indexes and B-Tree Indexes Differ

**MongoDB Search** uses a search-index model and stages like **$search/$searchMeta** on supported deployments. Do not confuse them with indexes created by db.collection.createIndex. Search indexes can update **asynchronously**, so search results may slightly lag behind writes.

Do not use search results as the authoritative source for final prices or inventory at checkout.

### 31.3. Tenant/Visibility in Search

Search queries must enforce scope:

~~~text
authenticated tenant
status ACTIVE
visibility PUBLIC
other ACL constraints
~~~

Do not rely on the frontend to filter out private data after the search backend returns it. With Search, check stage placement and version-specific filter/index semantics to enforce access controls directly in the query.

### 31.4. Combining Text and Facets

Approaches:

- Use a search engine for relevance, and filters/facets within the same system when supported.
- For a small bounded candidate set, retrieve IDs and query MongoDB for details.
- Use a normalized denormalized search projection.

Do not push hundreds of thousands of IDs through an unbounded **$in** query just to join two engines; establish pagination and consistency strategies.

## 32. Caching and Materialized Facet Counts

Facet counts can be cached by normalized filter:

~~~text
cache key:
  tenantId
  catalogVisibility
  categoryId
  canonicalFilterHash
  selfExcludingFacetId
  currency / market
  searchIndexVersion (if relevant)
~~~

### 32.1. Cache Keys Must Include Tenant Scope

If a cache key only contains categoryId+brandId without tenantId/visibility, counts from SHOP-A could be served to SHOP-B. That is a security/data isolation bug. Keys and authorization policies must align; never trust an unauthenticated tenant request header.

### 32.2. Cached Counts Can Be Stale

~~~text
Product activated
  -> MongoDB updated
  -> facet cache not invalidated yet
  -> UI displays old count
~~~

Decide on acceptable staleness, TTL/invalidation/refresh policies. Do not label unverified cached counts as “realtime exact”.

### 32.3. Materialized Facet Collection

~~~javascript
{
  _id: "SHOP-A|laptops|brand",
  tenantId: "SHOP-A",
  categoryId: "laptops",
  facetKey: "brandId",
  counts: [
    { value: "acer", count: 2 },
    { value: "dell", count: 1 },
    { value: "lenovo", count: 1 }
  ],
  computedAt: ISODate("2026-10-01T00:00:00Z")
}
~~~

These counts are only accurate for the **scope with no other filters applied**. They do not automatically produce exact counts once a user selects RAM≥16 and maxPrice≤30 million.

### 32.4. Do Not Materialize Every Combination

With dozens of facets and hundreds of values, storing every count combination explodes combinatorially. You can cache top queries, use the query engine for the long tail, and adopt a specialized search index when the workload warrants it.

## 33. Synchronizing Search Projections and Purchase Transactions

Large systems often follow a flow like:

~~~text
Product master + Category metadata
            |
            v
        Product events
            |
            v
Catalog search projection / MongoDB Search index
            |
            v
        Listing / Facets
            |
            v
     Product details API
            |
            v
Price + Inventory authority
            |
            v
       Checkout workflow
~~~

The search projection may contain **denormalized** fields like brand label, availableVariantOptions, min price, and category ancestry. It is a **read model**, not the single source of truth for inventory and pricing.

### 33.1. Out-of-Order Events

For example:

~~~text
T1: price set to 22M (revision=10)
T2: price set to 20M (revision=11)
Event revision=11 processed
Event revision=10 arrives late
~~~

If the consumer does not check revisions, the search projection could revert to 22M. Idempotent event handlers, version guards, or ordered partitioning suited to the data model are needed.

### 33.2. Change Streams Have Limitations

MongoDB change streams can aid change synchronization on suitable replica set/sharded topologies, but require resume tokens, consumer lag handling, and an adequate oplog retention window. Do not treat change streams as automatic “exactly-once business side effects”; consumers must still enforce idempotency and safe replay/duplicate handling.

### 33.3. Rapidly Changing SKU Stock

If availability is a filter read thousands of times, a compact search projection may be needed to avoid joining realtime inventory on every listing. However, the UI must accept lag per policy, and checkout must re-check inventory with concurrency safeguards.

### 33.4. When a Product Is Discontinued

A product with **status=ARCHIVED** must disappear from public listings/search. If the read model updates slowly, it may temporarily appear in results. The details API and checkout backends must still verify status from an authoritative source before allowing a purchase.

## 34. Authorization and Preventing Data Leaks in the Catalog

A public catalog does not mean every field of a product is public.

### 34.1. Data Categories

| Group | Example | Typical Policy |
|---|---|---|
| Public listing | title, thumbnail, public price | Can be exposed |
| Public specs | RAM, storage, color | Per category/approval |
| Seller private | supplierCost, margin | Never expose publicly |
| Moderator metadata | reviewFlags, moderationNotes | Internal only |
| Tenant private | unpublished products | Do not let other tenants read |
| Personalization | viewedBy, segments | May be PII, subject to separate policy |

A flexible attributes object must not become a dumping ground for sensitive data that gets serialized wholesale into responses.

### 34.2. Authorization Before Aggregation

In faceted search, **tenantId/status/visibility** must be applied properly from the start. An aggregation group can leak information via counts even without returning product details. Never treat “only returning counts” as exempt from authorization.

### 34.3. Do Not Expose supplierCost as a Public Facet

If the backend turns all attributes into facets via **$objectToArray**, a wholesale cost field could leak as a count or value. The registry must distinguish public-filterable vs. internal-only fields, and data flows must be reviewed.

### 34.4. Resource Limits

Users could submit excessive facet values or filter a massive category. Apply:

- Rate limits.
- Query complexity limits.
- Max page size.
- Timeouts/maxTime.
- Bounded aggregation outputs.
- Properly tenant-scoped caching.

Authorization bugs are never solved by merely filtering results on the frontend.

## 35. Testing Catalog Filtering on Representative Data

Tests must verify **query logic**, **BSON types**, **tenant isolation**, **facet counts**, and **index performance**. A query returning correct results on a tiny dataset does not prove it runs fast at millions of products.

### 35.1. Test Matrix with Sample Data

| Condition | Expected result |
|---|---|
| SHOP-A, laptops, ACTIVE/PUBLIC | L-101, L-102, L-103, L-104 |
| SHOP-A, laptops, brand=acer | L-101, L-104 |
| SHOP-A, laptops, ramGB≥16 | L-101, L-103, L-104 |
| SHOP-A, laptops, priceVnd≤20M | L-102 |
| SHOP-A, laptops, brand=acer, ramGB≥16, price≤30M | L-101 |
| SHOP-A, laptops, storageGB=1024 | L-103, L-104 |
| SHOP-A, phones, storageGB=256 | P-101 |
| SHOP-A, shoes, brand=puma | S-101 |
| SHOP-A, laptops, brand=acer, ram≥64 | No results |
| SHOP-B, laptops, brand=acer | L-X (no SHOP-A records) |

The examples have no availability filter for laptops because the sample products do not include inventory. Do not assume products with ACTIVE status are always in stock.

### 35.2. Testing $elemMatch Against False Positives

Create a variant document:

~~~javascript
db.variantsLab.insertOne({
  _id: "V-CROSS",
  variants: [
    { color: "black", sizeEU: 40, availableQty: 2 },
    { color: "black", sizeEU: 41, availableQty: 0 },
    { color: "white", sizeEU: 41, availableQty: 3 }
  ]
});
~~~

Query:

~~~javascript
db.variantsLab.find({
  variants: {
    $elemMatch: {
      color: "black",
      sizeEU: 41,
      availableQty: { $gt: 0 }
    }
  }
});
~~~

must **not return V-CROSS**. If a query using independent dotted paths returns V-CROSS, the test has caught the false-positive bug to guard against.

### 35.3. Testing Attribute Pattern Key/Value in the Same Element

~~~javascript
db.attrLab.insertOne({
  _id: "A-CROSS",
  attributes: [
    { key: "ramGB", valueNum: 8 },
    { key: "storageGB", valueNum: 1024 }
  ]
});
~~~

The query **$elemMatch: {key:"ramGB", valueNum:{$gte:16}}** must not match. However, a query using independent **attributes.key="ramGB"** and **attributes.valueNum≥16** can falsely match.

### 35.4. Testing OR vs. AND

With **brand in [acer,dell]** and **RAM≥16**, results are **L-101, L-103, L-104** when no price filter is applied.

With **brand=acer AND brand=dell** on a scalar field, no product has both brand IDs. A typical brand multi-select requires OR/$in, not combining two equality predicates with AND.

### 35.5. Testing Facet Counts

With no filters beyond category:

~~~text
brands: acer=2, dell=1, lenovo=1
RAM: 8=1, 16=2, 32=1
total=4
~~~

Selecting **brand=acer, RAM≥16**, self-excluding counts:

~~~text
items: L-101, L-104
total=2
brands (omitting brand filter): acer=2, dell=1
RAM (omitting RAM filter): 16=1, 32=1
~~~

If the UI wants conjunctive counts, the results differ and tests must follow the chosen contract.

### 35.6. Testing by Status and Permissions

Add a product:

~~~javascript
{
  _id: "L-PRIVATE",
  tenantId: "SHOP-A",
  categoryId: "laptops",
  status: "DRAFT",
  visibility: "PRIVATE",
  brandId: "acer",
  priceVnd: NumberLong("1000000"),
  attributes: { ramGB: 128 }
}
~~~

Public listings/brand facets/RAM facets must **exclude this product**. A missing filter can leak information via counts even if the items branch happens to omit it.

### 35.7. Testing Sorting and Pagination

Create two products with identical priceVnd and verify that **priceVnd + _id** sorting is deterministic. Page through results and confirm there are no duplicate IDs under static data.

When prices update between pages, test the accepted behavior (eventual consistency, cursor invalidation, or snapshot policy) instead of assuming offsets are always stable.

### 35.8. Testing Invalid Inputs

- ramGBMin=abc: validation error.
- ramGBMin=-1: validation error.
- priceMax=NaN: validation error.
- Non-existent category: 404/empty per API contract.
- Non-filterable facet key: reject.
- Client-supplied tenantId differing from authenticated identity: deny access.
- Oversized limit: reject/cap per policy.
- Arbitrary sort field outside allowlist: reject.
- Overly long multi-value list: reject.

### 35.9. Java/Spring Data Integration Tests

Test against a real MongoDB instance in an isolated environment (container/test cluster) for:

- Native Driver **Filters.elemMatch**.
- Spring Data **Criteria.elemMatch**.
- Numeric serialization **Long/Decimal128/Integer**.
- **$facet** aggregation and nested DTOs.
- **$objectToArray** on the attributes object.
- Index planner behavior on a more production-like dataset.

Unit tests that only mock repositories cannot verify index performance or MongoDB's real BSON query semantics.

## 36. Runbook for Tuning a Slow Catalog Filter

### Step 1 — Lock Down the Query Shape

Record:

~~~text
tenant scope:
category:
selected facets:
sort order:
page size:
schema model:
attribute type:
source of price/availability:
~~~

Do not compare two queries with different categories/selectivity and treat them as the same workload.

### Step 2 — Verify Result Correctness

A query may run very fast because it **filters incorrectly**. Check:

- Are tenantId/status/visibility present?
- Does multi-select brand use OR or AND properly?
- Do numeric ranges use the right BSON type?
- Do SKU color/size/stock match within the same element?
- Do counts measure products or SKUs?

### Step 3 — Inspect executionStats

Measure keys/docs examined, nReturned, sort, index, memory/spills, and duration. For Atlas Search, inspect Search-specific diagnostics instead of using B-tree explain to interpret search-index execution.

### Step 4 — Evaluate Suitable Indexes

If queries always include tenant/category/status and sort by price, consider a compound equality/sort index. If Attribute Pattern queries use $elemMatch, examine a compound multikey index on key/value. If workloads are highly varied, evaluate wildcard indexes with explain.

### Step 5 — Assess Cardinality and Data Skew

A category has one million documents, and one brand accounts for 70%; a query filtering that brand is still large. Adding indexes cannot reduce the volume of data scanned when a filter has low selectivity. Better pagination, caching, or search projections may be needed.

### Step 6 — Trim Output Data

Project only fields needed for listings, cap page sizes, and avoid $lookup on all variants/suppliers for every product.

### Step 7 — Limit Facet Branch Costs

If $facet has many branches performing large groups/sorts, split queries, cache slowly changing counts, or materialize popular dimensions.

### Step 8 — Re-measure Under Load

Monitor:

- p50/p95/p99 latency.
- CPU/IO/working set.
- MongoDB connections and pool wait time.
- Facet cache hit rate/freshness.
- Search index lag.
- Price/inventory projection freshness.
- Index size/write amplification.

Do not rely on a single explain over 8 products as the sole basis for production design.

## 37. Common Catalog Design and Query Pitfalls

### 37.1. Renaming an Attribute in the UI While Queries Still Use the Old Key

**Symptom:** users filter by RAM, yet many laptops are missing.

**Cause:** some documents use **memoryGB**, while others use **ramGB**.

**Fix:** canonical key registry, phased migration of old/new keys, and query coverage checks. Do not just change the UI label.

### 37.2. Numeric Filtering on Strings

**Symptom:** users select RAM≥16, but products storing ramGB="32" do not match.

**Cause:** BSON String differs from Numeric.

**Fix:** validate and normalize types at ingestion; backfill legacy data. Never run text-based range comparisons for numeric values.

### 37.3. Matching Two Attributes from Different Array Elements

**Symptom:** a laptop with RAM 8/SSD 1024 falsely satisfies RAM≥16 in the Attribute Pattern.

**Cause:** using independent dotted predicates instead of $elemMatch.

**Fix:** use $elemMatch to bind key and value to the same element.

### 37.4. Product Matches Non-Existent Color/Size on the Same SKU

**Symptom:** UI shows “black, size 41, in stock”, but checkout finds no matching SKU.

**Cause:** relying on independent colors[], sizes[], and hasStock[] fields.

**Fix:** query the same variant via $elemMatch or a variant collection with a compound filter; re-verify inventory at checkout.

### 37.5. Facet Counts Multiplied by Variant Count

**Cause:** unwinding variants and counting all rows instead of counting distinct productId when the UI wants product counts.

**Fix:** group by (productId, facetValue), then group by facetValue.

### 37.6. Facet Counts Do Not Change When Filters Are Selected

**Cause:** the app uses static per-category cached counts instead of computing dynamic filters.

**Fix:** define conjunctive/self-excluding behavior, compute counts per scope and active filters; if cached, clearly indicate freshness/approximation.

### 37.7. Brand Facet Leaves Only One Option

**Cause:** computing the Brand facet after applying brand=acer in the common $match.

**Fix:** if the UI requires self-excluding facets, omit the brand filter **only in the Brand branch**, while keeping all other filters.

### 37.8. $facet Returns an Oversized Document

**Cause:** each branch returns tens of thousands of values or unbounded items, exceeding memory/document limits.

**Fix:** top N, bounded arrays, pagination, split queries, or materialized counts. allowDiskUse does not fix every $facet limit.

### 37.9. Wildcard Index Exists Yet Queries Are Still Slow

**Cause:** unsuitable compound filter/sort, overly broad index, low selectivity, or fetching too many documents.

**Fix:** run explain, compare compound indexes for common queries, and reduce index bloat.

### 37.10. Indexing Every Attribute Slows Writes

**Cause:** too many indexes, increasing write amplification and storage.

**Fix:** measure query traffic, retire unused indexes systematically, only index top facets, and consider wildcard for the long tail when appropriate.

### 37.11. Cache Returns Another Tenant's Data

**Cause:** cache key lacks tenantId/visibility, or the app trusts an unauthenticated client tenantId.

**Fix:** treat as a security incident, fix canonical cache keys/scopes, and audit authorization end-to-end.

### 37.12. Public Listing Exposes supplierCost

**Cause:** returning the entire product Document, or dynamic facets pulling all attribute values.

**Fix:** enforce projections/DTOs/registry allowlists per role; never expose internal fields in JSON responses.

### 37.13. Archived Products Still Appear in Search

**Cause:** stale cache or search projection, or missing status filter.

**Fix:** check ingestion/events, freshness, and authorization at details/checkout. Do not just hide items on the frontend.

### 37.14. Display Price Differs from Checkout Price

**Cause:** stale materialized min price/offer cache, or differing currency/promotion conditions.

**Fix:** clearly define listing price, measure freshness, and lock prices from an authoritative service during order placement.

### 37.15. Offset Pagination Duplicates Products

**Cause:** products added/removed/re-priced during browsing, or sorting lacks a tie-breaker.

**Fix:** sort by price+_id, consider keyset/snapshot policies, and handle eventual changes appropriately for the product UX.

### 37.16. New Index Cannot Be Used for Sorting

**Cause:** index field order mismatches the query, brand sits between the equality prefix and price while the query omits brand, or sorting on a computed field.

**Fix:** check compound index order and explain; never assume having an index suffices.

### 37.17. Grouping Products Without the Attribute

**Symptom:** the RAM facet has a huge null bucket.

**Cause:** grouping RAM over a category where many products lack ramGB or have the wrong type.

**Fix:** match category and numeric type before grouping; design an explicit unknown bucket if the UI needs one.

### 37.18. Brand ID and Label Mixed Together

**Symptom:** facet displays Acer, ACER, Acer Inc. as three separate values.

**Cause:** failing to normalize brand IDs at import.

**Fix:** use stable brandIds, store localized labels separately, and maintain alias mappings.

### 37.19. Multi-Select Accidentally Uses AND

**Symptom:** selecting Acer and Dell yields 0 products.

**Cause:** backend combines two equality filters on the same scalar field with AND.

**Fix:** use $in per the OR-within-a-facet policy.

### 37.20. Querying Parent Category Misses Descendants

**Cause:** querying categoryId="electronics" while products only store leaf "laptops"/"phones".

**Fix:** query categoryAncestorIds or resolve descendant categories with indexing/caching and taxonomy synchronization.

### 37.21. Inventory Filter Only Checks Product-Level Total

**Cause:** hasAvailableVariant=true even though the selected color/size variant is out of stock.

**Fix:** query availability on the same variant, re-check at checkout.

### 37.22. Attribute Data Changes Without Facet Counts Updating

**Cause:** cache invalidation/changelog consumer lag, or materialized counts are not updated.

**Fix:** monitor event versions, consumer lag, cache freshness, and perform periodic reconciliation.

### 37.23. Seller Enters the Same Attribute Twice

**Cause:** Attribute Pattern lacks single-valued key validation; a unique multikey index does not enforce intra-document uniqueness as expected.

**Fix:** validate unique keys at ingestion; write tests and a cleanup process for duplicates.

### 37.24. Slow Regex/Autocomplete

**Cause:** arbitrary substring regex over large datasets where standard indexes are suboptimal.

**Fix:** define clear search requirements, consider dedicated Search/autocomplete, and enforce query limits.

### 37.25. Wrong Filter Results After Unit Conversion

**Cause:** storage=0.5TB mistakenly imported as storageGB=0.5, breaking range queries.

**Fix:** run migrations with unit-aware conversion, versioning, and validation; do not merely rename fields.

## 38. Operational Rules as the Catalog Grows

### 38.1. Separating Read and Write Responsibilities

Reference workflow:

~~~text
Seller input
   |
   v
Validate product/category/attribute registry
   |
   v
Canonical master data + variants/offers
   |
   v
Change events / outbox
   |
   v
Search projection + cached/materialized facets
   |
   v
Public catalog APIs
~~~

Ingestion must enforce types/units/identity. Search projections optimize reads; checkout uses authoritative stock/price.

### 38.2. Per-Category Observability

Measure latency and workload segmented by category groups of reasonable cardinality, while avoiding metric labels containing thousands of product IDs. A category with 99% of queries and millions of products needs different indexing/compute than a rare category with 100 records.

### 38.3. Controlled Search Data Refreshes

When millions of attributes are migrated:

- Throttle writes to avoid overload.
- Monitor replication/search index lag.
- Ensure event consumers are idempotent.
- Reconcile missed documents.
- Enable new filters only after data/indexes are ready.

### 38.4. Bounding Document Growth

A product with tens of thousands of variants, reviews, inventory history, and media files must not be stuffed into a single document. MongoDB has a BSON document size limit; unbounded arrays make reads and updates hard to manage. Split data with different lifecycles into appropriate collections.

### 38.5. Defining SLOs and Freshness

Example target groups:

~~~text
Catalog listing p95 latency:
Facet count p95 latency:
Search index freshness:
Price projection freshness:
Stock projection freshness:
Maximum allowed page size:
Maximum active query time:
~~~

Fill in actual numbers based on product requirements and real benchmarks; do not treat sample figures as MongoDB defaults.

## 39. Hands-On Exercises: Schema and Query Design

Exercises use the **catalog_lab** database and sample data from section 4 unless a prompt supplies its own document. Run them in a test database with appropriate permissions.

### Exercise 1. Choosing Common Fields vs. Category-Specific Fields

A catalog has laptops, phones, and shoes.

**Question:** which fields should be standardized on the product and which should vary by category?

**Guidance:** tenantId, categoryId, brandId, title, status, visibility, and price or offer reference are typically core fields. ramGB/storageGB/batteryMAh/material can be per-category. Avoid mixing all category-specific fields into the top level without clear rules.

### Exercise 2. Filtering Acer Laptops

**Requirement:** find SHOP-A, ACTIVE/PUBLIC products in laptops with brand=acer.

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  categoryId: "laptops",
  brandId: "acer",
  status: "ACTIVE",
  visibility: "PUBLIC"
});
~~~

**Answer:** L-101 and L-104.

### Exercise 3. Filtering RAM and Price

**Requirement:** RAM≥16, priceVnd≤30M, laptops from SHOP-A.

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  categoryId: "laptops",
  "attributes.ramGB": { $gte: 16 },
  priceVnd: { $lte: NumberLong("30000000") }
});
~~~

**Answer:** L-101. For real public queries, add status ACTIVE and visibility PUBLIC.

### Exercise 4. Filtering Multiple Brands

**Question:** if the user selects Acer or Dell, what should be used?

**Answer:**

~~~javascript
{ brandId: { $in: ["acer", "dell"] } }
~~~

Do not AND two equality predicates on the same scalar brandId field.

### Exercise 5. Storage Among Multiple Choices

**Requirement:** storageGB in [256,1024] for SHOP-A laptops.

**Answer:** L-102, L-103, and L-104. L-101 has 512, which is not in the list.

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  categoryId: "laptops",
  "attributes.storageGB": { $in: [256, 1024] }
});
~~~

### Exercise 6. String vs. Number Bug

Document:

~~~javascript
{ attributes: { ramGB: "16" } }
~~~

**Question:** why is a numeric ramGB≥16 query unreliable here?

**Answer:** BSON String is not Numeric; normalize data to numbers before running range queries.

### Exercise 7. Single-Valued Attribute

A Product Attribute Pattern contains two elements with key=ramGB, valueNum=8 and 32.

**Question:** can we be sure ramGB≥16 accurately reflects the product?

**Answer:** no. The single-valued key is duplicated; validation and data cleanup are needed. A unique multikey index does not replace per-entry duplicate checking within a single document.

### Exercise 8. $elemMatch with the Attribute Pattern

~~~javascript
{
  attributes: [
    { key: "ramGB", valueNum: 8 },
    { key: "storageGB", valueNum: 1024 }
  ]
}
~~~

**Question:** how do we avoid falsely matching RAM≥16?

**Answer:**

~~~javascript
{
  attributes: {
    $elemMatch: {
      key: "ramGB",
      valueNum: { $gte: 16 }
    }
  }
}
~~~

### Exercise 9. Two Different Attributes

**Requirement:** RAM≥16 and SSD≥512 in the Attribute Pattern.

**Guidance:** use **$all** containing two **$elemMatch** clauses or **$and** of two $elemMatch clauses on the same array field; each element binds its key to the right value without requiring one element to hold both keys.

### Exercise 10. Matching SKU on Same Color, Size, and Stock

Variants:

~~~javascript
[
  { color: "black", sizeEU: 41, availableQty: 0 },
  { color: "white", sizeEU: 41, availableQty: 3 }
]
~~~

**Question:** does the product satisfy black/size41/inStock=true?

**Answer:** no. Use $elemMatch on variants so the same element satisfies all three predicates.

### Exercise 11. Distinguishing Product Count vs. SKU Count

A product has three red SKUs, two of which are in stock.

**Question:** if the UI facet reads “Red: product count”, should it count 1 or 2/3?

**Answer:** count **1 product** if at least one red SKU meets the current conditions; SKU count is a different metric. Group/deduplicate by productId.

### Exercise 12. Finding Products Under a Parent Category

The product only stores categoryId="laptops", categoryAncestorIds=["electronics","computers"].

**Question:** does filter categoryId="electronics" match? How do we find them?

**Answer:** no; query categoryAncestorIds="electronics" or resolve descendant categories via the taxonomy.

### Exercise 13. Is Defaulting to 0 Correct?

A pair of shoes does not have batteryMAh. A developer sets batteryMAh=0 to avoid null.

**Question:** is this good practice?

**Answer:** no if battery does not apply; 0 is a numeric value distinct from unknown/not-applicable. Model missing/NA explicitly.

### Exercise 14. Basic Facet Counts

**Question:** for SHOP-A/laptops ACTIVE/PUBLIC, what are the counts by brand?

**Answer:** acer=2, dell=1, lenovo=1.

### Exercise 15. Facet by RAM

**Question:** for the 4 SHOP-A laptops, what is the RAM facet?

**Answer:** RAM 8=1, RAM 16=2, RAM 32=1.

### Exercise 16. Self-Excluding Brand

User selects brand=acer and RAM≥16.

**Question:** what values does the self-excluding Brand facet have?

**Answer:** acer=2, dell=1. When computing Brand, omit the brand filter while keeping RAM≥16, so Lenovo RAM8 does not match.

### Exercise 17. Self-Excluding RAM

Same conditions as Exercise 16.

**Question:** what is the self-excluding RAM facet?

**Answer:** 16=1 and 32=1. When computing RAM, omit the RAM filter while keeping brand=acer.

### Exercise 18. Counts After Pagination

A query has 100 matching products and returns a page size of 24.

**Question:** should totalCount be 100 or 24?

**Answer:** 100 if the UI requires the exact total matching products. 24 is only the row count of the current page.

### Exercise 19. $facet and Common Match

**Question:** why not put match brand=acer before $facet if we want Brand to be self-excluding?

**Answer:** the Brand branch cannot recover brands already filtered out in an earlier stage. Put tenant/category/status/visibility in the common match; place facet-excludable filters inside the appropriate branches.

### Exercise 20. Grouping Arrays of Values

A product has ports=["USB-C","HDMI"].

**Question:** does $objectToArray followed by grouping on the ports value automatically count each port separately?

**Answer:** no. The value is still an array; unwind/normalize and then deduplicate product+port if counting products.

### Exercise 21. Choosing an Index for Listings

Frequent query: tenantId + categoryId + status + visibility, sorted by ascending priceVnd and ascending _id.

**Guided answer:**

~~~javascript
db.products.createIndex({
  tenantId: 1,
  categoryId: 1,
  status: 1,
  visibility: 1,
  priceVnd: 1,
  _id: 1
});
~~~

Verify with explain under a real workload.

### Exercise 22. Index Containing brandId

**Question:** does an index on tenant/category/status/visibility/brandId/priceVnd always serve price sorting if brand is not filtered?

**Answer:** no. Having brandId before price can prevent the index from serving a global price sort when brand has no equality constraint.

### Exercise 23. Compound Multikey on Two Arrays

A product has independent colors[] and sizesEU[]. A developer wants a compound index on both.

**Answer:** MongoDB compound multikey indexes restrict parallel arrays; moreover, two separate arrays do not preserve the color-size relationship. Use variants in the same element or a SKU collection.

### Exercise 24. Wildcard Index

**Question:** does wildcard index attributes.$** automatically replace compound indexes for category+brand+price+RAM?

**Answer:** no. Wildcard helps with dynamic paths but does not automatically optimize all compound predicates and sorts.

### Exercise 25. Partial Index

A partial index only includes status=ACTIVE and visibility=PUBLIC.

**Question:** can an admin query for ARCHIVED use this index to return all documents?

**Answer:** it cannot rely on this partial index alone because the index excludes documents outside its filter.

### Exercise 26. Facet Counts and Security

A public facet returns RAM=128:1 for a PRIVATE product.

**Question:** what is the bug?

**Answer:** permissions/scope were not applied in the facet branch, leaking information via counts. Enforce a common match on tenant/status/visibility and authorization.

### Exercise 27. Multi-Currency Prices

**Question:** can 20,000,000 VND and 900 USD be compared directly under the same priceMax without conversion?

**Answer:** no. Consistent currency and conversion/scale rules are required.

### Exercise 28. Sorting with Duplicate Prices

Two products share the same priceVnd. The query sorts only by priceVnd.

**Question:** what is the pagination problem?

**Answer:** the ordering of equally priced items is non-deterministic; use priceVnd + _id as a tie-breaker.

### Exercise 29. Keyset Cursor

The end of a page has (price=22M, _id="L-101"). The next page by ascending price needs:

~~~javascript
{
  $or: [
    { priceVnd: { $gt: NumberLong("22000000") } },
    {
      priceVnd: NumberLong("22000000"),
      _id: { $gt: "L-101" }
    }
  ]
}
~~~

Combine this with tenant/category/status/visibility and the corresponding sort.

### Exercise 30. Dynamic Facets and Private Data

An attribute object contains internalCost and serialNumber.

**Question:** can all entries from $objectToArray be exposed as public facets?

**Answer:** no. Only keys allowed as visible/filterable by the registry and permitted for the user may be exposed.

### Exercise 31. Listing Inventory Differs from Checkout

A cached listing shows color=black,size41 is in stock, but inventory ran out before checkout.

**Question:** can the order be confirmed based on the listing?

**Answer:** no. Checkout must confirm quantities from the authoritative source and handle concurrency/reservation.

### Exercise 32. Cache Missing Tenant

A cache key only has category=laptops,brand=acer without tenantId.

**Question:** what is the risk?

**Answer:** leaking or mixing products/facet counts across tenants. Keys must bind the authenticated tenant scope as well as visibility/market.

### Exercise 33. Renaming Legacy Keys

Old field attributes.storage="512 GB"; new field attributes.storageGB=512.

**Question:** is changing the UI label enough?

**Answer:** no. You need expand readers/writers, parse/convert old data, backfill, reconcile, switch indexes, and contract.

### Exercise 34. Partial SKU Match

A product has:

~~~javascript
[
  { color: "black", sizeEU: 40, availableQty: 1 },
  { color: "white", sizeEU: 41, availableQty: 1 }
]
~~~

**Question:** does the product have black size41 in stock?

**Answer:** no. Color and size do not belong to the same variant.

### Exercise 35. Designing a Multi-Vertical Catalog

A marketplace has 300 categories and 4 million products:

~~~text
80% requests: category + brand + price sort
15% requests: category + one numeric facet
5% requests: long-tail spec filters
~~~

**Requirement:** propose schema/indexes.

**Guidance:** core fields for category/brand/status/price, hybrid or object attributes with a registry; compound indexes for top patterns, category-specific indexes for needed numeric facets, and evaluate wildcard for the long tail after measurement. Do not index every permutation.

### Exercise 36. Validating FilterSpec

Backend receives:

~~~javascript
{
  category: "laptops",
  attribute: "ramGB",
  min: "16",
  sort: "price_asc"
}
~~~

**Guided answer:** obtain tenant from auth, validate filterable category/attribute, parse "16" into a Number, validate range, allowlist sort, bound page size/query complexity, and construct the BSON query from code-controlled operators.

### Exercise 37. IXSCAN Yet Still Slow

A query scans 600,000 index entries and returns 24 products.

**Question:** is seeing IXSCAN enough to conclude the query is good?

**Answer:** no. Check keys/docs examined, selectivity, sort stages, and data distribution. A different index/query or workload limit may be needed.

### Exercise 38. Designing a Facet Dashboard

Requirement:

~~~text
Category laptops
Selected: Acer, RAM >= 16
Show items + total + Brand counts + RAM counts
Brand counts show alternative brands
RAM counts show alternative RAM values
~~~

**Guidance:** common match on tenant/category/status/visibility; items+total branches apply Acer+RAM; Brand branch applies only RAM; RAM branch applies only Acer. Do not put both filters before $facet.

### Exercise 39. Product with Too Many Variants

A product has 50,000 SKUs with continuously updating inventory.

**Question:** should all SKUs and stock be embedded in the product document?

**Guidance:** consider splitting into a SKU/inventory collection to avoid document growth/contention, use a bounded search projection for listings, and re-verify at checkout.

### Exercise 40. Product Count from SKU Rows

There are 1,000 products and 2,500 SKUs. The user selects color black, size41, stock>0 and the UI reads “42 products”.

**Question:** what must the aggregation guarantee?

**Answer:** filter color+size+stock on the same variant, then deduplicate by productId before counting, avoiding returning 42 SKU rows labeled as 42 products.

## 40. Pre-Implementation Catalog Design Checklist

### 40.1. Data Model

- [ ] Distinguished product, variant/SKU, offer, and inventory.
- [ ] Consistent core fields for tenant/category/brand/status/visibility.
- [ ] Per-category attribute registry with types, units, and filter semantics.
- [ ] Identified which attributes are single-valued, multi-valued, or variant-specific.
- [ ] Avoided storing arbitrary Strings for numeric filters.
- [ ] Clear strategy for missing/null/unknown/not-applicable.
- [ ] Bounded array/document growth and lifecycle for rapidly changing data.

### 40.2. Queries and Facets

- [ ] AND between facets and OR within a facet are clearly defined.
- [ ] $elemMatch is used when predicates must match the same array element.
- [ ] Facet count unit (product vs. SKU) is explicitly declared.
- [ ] Facet counts enforce tenant/status/visibility properly.
- [ ] Conjunctive vs. self-excluding facet semantics align with the UI.
- [ ] Facets for array/multi-valued keys are properly deduplicated.
- [ ] Number of facets and values returned by the API is bounded.
- [ ] Pagination is stable and total count semantics are clear.

### 40.3. Indexes and Performance

- [ ] Compound indexes are based on real top query shapes.
- [ ] Multikey indexes respect array path restrictions.
- [ ] Wildcard indexes are used only after understanding limits and measuring workloads.
- [ ] explain executionStats verified on a representative dataset.
- [ ] Limits set on sort/page size/execution time/query complexity.
- [ ] Caching/materialized counts strategy defined where needed.
- [ ] Index write amplification and storage overhead accounted for.

### 40.4. Security and Integration

- [ ] Tenant derived from authenticated context.
- [ ] Public responses only include permitted fields.
- [ ] Dynamic attribute queries allowlisted and validated.
- [ ] Private specs/supplier costs excluded from dynamic facets.
- [ ] Search projections have freshness policies and handle out-of-order events.
- [ ] Checkout verifies authoritative price/inventory.
- [ ] Contract tests in place for downstream consumers/feeds.
- [ ] Migration plan prepared for category/attribute definition changes.

### 40.5. Operations

- [ ] Metrics for query/facet p95/p99, error rate, index usage, and lag.
- [ ] Integration tests covering $elemMatch false positives.
- [ ] Tenant isolation tests for both items **and** facet branches.
- [ ] Tests for numeric types, unit conversion, and boundary conditions.
- [ ] Tests distinguishing product count vs. SKU count.
- [ ] Runbook ready when Search/index/cache go out of sync.
- [ ] Schema/index rollback plan ready before major changes.

## 41. API Contract for Listings and Facets

A response should clearly present **displayed products**, **total matching products**, and **count semantics**:

~~~javascript
{
  categoryId: "laptops",
  items: [
    {
      productId: "L-101",
      title: "Acer Swift A14",
      brandId: "acer",
      price: {
        amountMinor: 22000000,
        currency: "VND"
      }
    },
    {
      productId: "L-104",
      title: "Acer Creator 16",
      brandId: "acer",
      price: {
        amountMinor: 40000000,
        currency: "VND"
      }
    }
  ],
  page: {
    size: 24,
    nextCursor: null,
    totalProducts: 2
  },
  facets: {
    semantics: "self-excluding",
    brand: [
      { value: "acer", productCount: 2 },
      { value: "dell", productCount: 1 }
    ],
    ramGB: [
      { value: 16, productCount: 1 },
      { value: 32, productCount: 1 }
    ]
  }
}
~~~

This example illustrates the **SHOP-A/laptops/brand=acer/RAM≥16** filter without adding a price limit. In JSON over HTTP, integer VND amounts should follow an exact contract; if values can exceed JavaScript's safe Number limit, consider decimal Strings or an API schema supporting big integers.

### 41.1. Decisions to Document in the API Specification

- Is **totalProducts** exact or cached/estimated?
- Which selected filters are **facet productCounts** computed over?
- Can **facets** lag behind realtime inventory updates?
- Is **nextCursor** bound to tenant/filter/sort?
- Is **Price** the base price, min offer, promotional price, or final checkout price?
- Do **unknown attribute values** have a separate bucket?
- Are **zero counts** displayed in the UI?
- Are **brand labels** fetched from the localized registry or from product snapshots?

An API lacking these definitions can return completely valid MongoDB data while creating a confusing filtering experience.

## 42. References

In production implementations, select documentation matching your project's **MongoDB server version**, **Java Driver version**, and **Spring Data MongoDB version**:

- [MongoDB Manual — Query Documents](https://www.mongodb.com/docs/manual/tutorial/query-documents/)
- [MongoDB Manual — Query Arrays](https://www.mongodb.com/docs/manual/tutorial/query-arrays/)
- [MongoDB Manual — Query Arrays of Embedded Documents](https://www.mongodb.com/docs/manual/tutorial/query-array-of-documents/)
- [MongoDB Manual — $elemMatch](https://www.mongodb.com/docs/manual/reference/operator/query/elemMatch/)
- [MongoDB Manual — $all](https://www.mongodb.com/docs/manual/reference/operator/query/all/)
- [MongoDB Manual — Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/)
- [MongoDB Manual — Wildcard Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-wildcard/)
- [MongoDB Manual — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB Manual — Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/)
- [MongoDB Manual — $facet](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/)
- [MongoDB Manual — $bucket](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bucket/)
- [MongoDB Manual — $objectToArray](https://www.mongodb.com/docs/manual/reference/operator/aggregation/objectToArray/)
- [MongoDB Manual — $unwind](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/)
- [MongoDB Manual — $lookup](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Java Sync Driver — Query Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/)
- [Spring Data MongoDB — Template Query Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html)
- [Spring Data MongoDB — Aggregation Framework](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html)
- [MongoDB Search — Facet Operator](https://www.mongodb.com/docs/atlas/atlas-search/facet/)

Documentation URLs may change across versions; if a page moves, open the corresponding topic section in the official docs and select the matching version. Do not copy syntax for features not supported by your deployment.

## 43. Conclusion

A product catalog with variable attributes is not just a collection full of arbitrary fields. A proper design integrates **schema**, **query semantics**, **indexes**, **SKUs/offers/inventory**, **facets**, **API contracts**, and **data lifecycle**:

~~~text
                CATEGORY DEFINITIONS
                  /             \
                 v               v
          Attribute registry   Taxonomy
                 |               |
                 +-------+-------+
                         |
                         v
               CANONICAL PRODUCT DATA
                /        |         \
               v         v          v
           Attributes  Variants    Offers
               |         |          |
               +---------+----------+
                         |
                         v
                 SEARCH PROJECTION
                         |
           +-------------+--------------+
           |             |              |
           v             v              v
       Filter query   Facet counts   Sorting/paging
           |             |              |
           +-------------+--------------+
                         |
                         v
                  PUBLIC CATALOG API
                         |
                         v
                  PRODUCT SELECTION
                         |
                         v
               AUTHORITATIVE CHECKOUT
           (price and inventory re-check)
~~~

**Core Principles:**

1. **Identify core fields and category-specific attributes** before choosing an object, Attribute Pattern array, or hybrid schema.
2. **Values must have standardized types and units**. Numeric ranges on Strings or mismatched units cause logic bugs without MongoDB throwing syntax errors.
3. **The Attribute Pattern needs $elemMatch** so keys and values belong to the same element; multiple distinct attributes need proper condition combinations.
4. **Products and SKUs are not the same**. Filtering color/size/stock must match within the same variant, and counts must specify whether they count products or SKUs.
5. **Facets are semantic queries**, not mere groupings: define AND/OR, self-excluding behavior, exact/cached counts, and tenant scoping.
6. **Indexes serve query patterns**, rather than creating a wildcard index and assuming every filter/sort is optimized.
7. **The category registry is the data contract source**, governing types, units, allowed values, visibility, and cross-locale UI key mappings.
8. **Search projections can be stale**; checkout must not rely on cached stock/price and must re-confirm from authoritative sources.
9. **Pagination requires deterministic ordering** and clear consistency semantics when products/prices change across pages.
10. **Validation, authorization, migration, monitoring, and integration tests** are integral parts of catalog design, not afterthoughts added after the system grows too large.

When design decisions start from **the questions users actually want to filter by** and **the data unit the system must answer with**, MongoDB can store many product categories in one flexible model while querying accurately, scaling cleanly, and keeping business boundaries clear. The goal is not to cram everything into one document, but to ensure **data describes products accurately, filters produce exact results, and the system sustains performance as the catalog grows**.