# Polymorphic Documents and Representing Business Variants in MongoDB

## 1. Why Can One Collection Hold Multiple Document Shapes?

In relational databases, a table is typically defined by a shared set of columns for all rows. MongoDB stores data as **BSON documents** and does not require every document in the same collection to have an identical structure. This allows representing entities that **belong to the same business concept** while carrying different attributes per variant.

For example, an e-commerce platform offers three product types:

- **Physical goods (PHYSICAL):** require weight, warehouse SKU, and shipping method.
- **Digital goods (DIGITAL):** require a digital asset ID, license type, and download limit.
- **Subscriptions (SUBSCRIPTION):** require a plan code, billing interval, and trial days.

All three share **product code**, **name**, **status**, **price**, and **currency**. However, forcing every document to carry all fields of all three types creates many null values and obscures business rules.

**Polymorphic documents** organize one or more distinct document shapes behind a shared business interface. In MongoDB, a common implementation is the **Polymorphic Pattern**: documents with differing shapes are stored in **the same collection**, typically accompanied by a **discriminator field** identifying the variant.

### 1.1. Two Examples in the Same Collection

Physical product document:

~~~javascript
{
  _id: ObjectId("64b000000000000000000001"),
  tenantId: "SHOP-A",
  productCode: "KEYBOARD-01",
  kind: "PHYSICAL",
  name: "Mechanical Keyboard",
  status: "ACTIVE",
  price: {
    amount: NumberDecimal("1299000.00"),
    currency: "VND"
  },
  details: {
    inventorySku: "SKU-KB-001",
    weightGrams: NumberInt(850),
    shippingClass: "STANDARD"
  },
  schemaVersion: NumberInt(1)
}
~~~

Digital product document:

~~~javascript
{
  _id: ObjectId("64b000000000000000000002"),
  tenantId: "SHOP-A",
  productCode: "EBOOK-MONGO-01",
  kind: "DIGITAL",
  name: "MongoDB E-book",
  status: "ACTIVE",
  price: {
    amount: NumberDecimal("99000.00"),
    currency: "VND"
  },
  details: {
    assetId: "ASSET-MONGO-PDF",
    licenseType: "PERSONAL",
    maxDownloads: NumberInt(3)
  },
  schemaVersion: NumberInt(1)
}
~~~

Both documents share **common fields** while **details** differs by **kind**. MongoDB accepts this natively, though the application must enforce rules so documents remain valid.

### 1.2. When Should You Consider Polymorphic Documents?

Ask three questions:

1. Do the variants truly belong to **the same business entity**, or do they merely look similar by name?
2. Does the application frequently **search, paginate, display, authorize, or report jointly** across all variants?
3. Does each variant have some distinct fields/rules while still sharing **lifecycle, identity, and relationships** at a reasonable level?

If all three answers are yes, a polymorphic collection is worth considering. If the entity types have completely different lifecycles, permissions, query workloads, and indexes, separate collections may be better.

## 2. Modeling Mindset: What Is Shared vs. What Differs?

### 2.1. Separate Invariants from Variants

A clear design starts by defining:

- **Identity:** within what scope is a product code unique? For example, the **tenantId + productCode** pair.
- **Common invariants:** every product must have a name, status, price, and currency code, plus any other domain-wide invariants.
- **Discriminator:** the **kind** field with a controlled list of values.
- **Variant payload:** attributes meaningful only to a given **kind**, placed under **details**.
- **Schema version:** representation version enabling safe transitions as business logic evolves.

~~~text
Collection: products
|
+-- Common identity and lifecycle
|   +-- _id
|   +-- tenantId
|   +-- productCode
|   +-- name
|   +-- status
|   +-- price
|   +-- schemaVersion
|
+-- kind: discriminator
|   |
|   +-- PHYSICAL
|   |     +-- details.inventorySku
|   |     +-- details.weightGrams
|   |     +-- details.shippingClass
|   |
|   +-- DIGITAL
|   |     +-- details.assetId
|   |     +-- details.licenseType
|   |     +-- details.maxDownloads
|   |
|   +-- SUBSCRIPTION
|         +-- details.planCode
|         +-- details.billingInterval
|         +-- details.trialDays
~~~

With this structure, clients can fetch a unified list from **products**, then inspect **kind** to decide how to render or access variant data.

### 2.2. A Discriminator Is Part of the Data Contract

For example:

~~~javascript
kind: "PHYSICAL"
~~~

Do not infer the type from the presence of an arbitrary field:

~~~javascript
if (doc.details.weightGrams) {
  // Fragile inference: a value of 0 and a missing field can be misread.
}
~~~

An explicit discriminator helps with:

- **Queries:** filtering the exact variant with **{ kind: "PHYSICAL" }**.
- **Mapping:** Java/Node.js knows which domain object type to instantiate.
- **Validation:** enforcing variant-specific required fields.
- **Indexing:** creating indexes tailored to variant-specific queries.
- **Migration:** knowing which version/variant a document belongs to during schema upgrades.

Discriminator values must have stable business meaning. Renaming **DIGITAL** to **DOWNLOAD** merely because of a UI label change can break queries, validators, legacy data, and downstream consumers.

### 2.3. Distinguish Discriminator from schemaVersion

| Field | Question Answered | Example |
|---|---|---|
| **kind** | Which **business type** is this? | PHYSICAL, DIGITAL, SUBSCRIPTION |
| **schemaVersion** | Which **structural version** does this document use? | 1, 2 |
| **status** | Which **lifecycle state** is the entity currently in? | DRAFT, ACTIVE, ARCHIVED |

A DIGITAL product at **schemaVersion = 1** and a DIGITAL product at **schemaVersion = 2** remain the same business kind; only the storage layout changed. Switching from PHYSICAL to DIGITAL is usually a change in business nature, not just a schema version bump.

## 3. Complete Example: Three Product Variants

The following examples use **mongosh** syntax. Helpers like **ObjectId**, **NumberInt**, **NumberDecimal**, and **ISODate** construct specific BSON types; this is not plain JSON.

~~~javascript
use polymorphic_shop

db.products.insertMany([
  {
    tenantId: "SHOP-A",
    productCode: "KEYBOARD-01",
    kind: "PHYSICAL",
    name: "Mechanical Keyboard",
    status: "ACTIVE",
    price: {
      amount: NumberDecimal("1299000.00"),
      currency: "VND"
    },
    details: {
      inventorySku: "SKU-KB-001",
      weightGrams: NumberInt(850),
      shippingClass: "STANDARD"
    },
    schemaVersion: NumberInt(1),
    createdAt: ISODate("2026-01-10T08:00:00Z")
  },
  {
    tenantId: "SHOP-A",
    productCode: "EBOOK-MONGO-01",
    kind: "DIGITAL",
    name: "MongoDB E-book",
    status: "ACTIVE",
    price: {
      amount: NumberDecimal("99000.00"),
      currency: "VND"
    },
    details: {
      assetId: "ASSET-MONGO-PDF",
      licenseType: "PERSONAL",
      maxDownloads: NumberInt(3)
    },
    schemaVersion: NumberInt(1),
    createdAt: ISODate("2026-01-12T08:00:00Z")
  },
  {
    tenantId: "SHOP-A",
    productCode: "PRO-MONTHLY",
    kind: "SUBSCRIPTION",
    name: "Pro Monthly",
    status: "ACTIVE",
    price: {
      amount: NumberDecimal("199000.00"),
      currency: "VND"
    },
    details: {
      planCode: "PRO",
      billingInterval: "MONTH",
      trialDays: NumberInt(14)
    },
    schemaVersion: NumberInt(1),
    createdAt: ISODate("2026-01-15T08:00:00Z")
  }
]);
~~~

### 3.1. Why Not Put Every Attribute at the Top Level?

An alternative layout might be:

~~~javascript
{
  productCode: "EBOOK-MONGO-01",
  kind: "DIGITAL",
  name: "MongoDB E-book",
  weightGrams: null,
  shippingClass: null,
  assetId: "ASSET-MONGO-PDF",
  licenseType: "PERSONAL",
  planCode: null,
  billingInterval: null
}
~~~

A flat layout is still **valid in MongoDB**. However, as variants grow, documents fill up with meaningless fields, and validators and DTOs struggle to distinguish **absent fields**, **intentional nulls**, and **invalid values**.

Placing variant-specific parts inside **details** shows readers a clear boundary. Still, do not apply this rigidly: if a specialized attribute is frequently queried across multiple variants with identical semantics, keeping it in the common area may be more practical.

### 3.2. Must Every Document in the Same Collection Share the Exact Same Schema?

**No.** MongoDB allows flexible structures; what must remain stable is the **business contract**. When variants are intentionally modeled, differing fields are a feature. When each deployment accidentally introduces misspelled field names, mismatched types, or ambiguous shapes, that is **schema drift** that must be controlled.

Invalid example:

~~~javascript
{ kind: "PHYSICAL", details: { weightGram: "850" } }
{ kind: "PHYSICAL", details: { weightGrams: NumberInt(850) } }
~~~

Both documents can succeed on insert without a validator, yet code filtering on **details.weightGrams** misses the first document. **Schema flexibility** does not automatically guarantee consistency.

## 4. Common Polymorphic Patterns

### 4.1. Single Collection + Discriminator + Details

This is the approach used in our running example:

~~~text
products
├── { kind: PHYSICAL, details: {...} }
├── { kind: DIGITAL, details: {...} }
└── { kind: SUBSCRIPTION, details: {...} }
~~~

**Pros:** unified search, unified pagination, shared identity and lifecycle, easy sharing of base fields/indexes. **Cons:** collection holds multiple shapes; each variant needs matching validation and indexes.

### 4.2. Single Collection + Top-Level Variant Fields

~~~javascript
{
  productCode: "KEYBOARD-01",
  kind: "PHYSICAL",
  name: "Mechanical Keyboard",
  inventorySku: "SKU-KB-001",
  weightGrams: NumberInt(850)
}
~~~

Suitable when variants are small, distinct fields are few, and direct queries happen very frequently. The trade-off is that variant fields are no longer grouped under a recognizable namespace. There is no MongoDB rule mandating **details**; what matters is consistent, controllable organization.

### 4.3. Separate Collections per Variant

~~~text
physical_products
digital_products
subscription_products
~~~

Each collection has its own validator and indexes. This helps when each type has independent workloads, retention, permissions, record volumes, or lifecycles.

In return, querying **"all ACTIVE products of SHOP-A"** spans multiple collections, typically requiring application-level merging or `$unionWith` aggregation where suitable. Enforcing a unique **productCode** across collections is also harder than using a single-collection unique index.

### 4.4. Common Collection + Detail Collections

~~~text
products
  { _id, tenantId, productCode, kind, name, status, price }

physical_product_details
  { productId, weightGrams, inventorySku, shippingClass }

digital_product_details
  { productId, assetId, licenseType, maxDownloads }
~~~

This separates shared and variant data and lets types have different storage policies. However, it requires **joining via `$lookup` or multiple reads**, application-managed referential integrity, and potentially transactions for cross-collection updates.

Do not split details into separate collections just to mimic relational tables. If details are small and read alongside the product on nearly every request, **embedding** inside the document simplifies operations and provides single-document atomicity.

### 4.5. Mixed Pattern: Variants with Large or Outlier Fields

If only certain DIGITAL products have thousands of download logs, do not embed an unbounded array inside **details**:

~~~javascript
{
  kind: "DIGITAL",
  details: {
    assetId: "ASSET-123",
    // Do not store an ever-growing download history here.
    downloads: [ /* unbounded */ ]
  }
}
~~~

Download events belong in a separate events collection, such as **download_events**, linked via **productId**. MongoDB caps BSON documents at **16 MiB**; unbounded arrays strain RAM, I/O, and updates.

## 5. Querying Polymorphic Documents

### 5.1. Unified Search Across All Variants

~~~javascript
db.products.find(
  {
    tenantId: "SHOP-A",
    status: "ACTIVE"
  },
  {
    _id: 1,
    productCode: 1,
    kind: 1,
    name: 1,
    price: 1
  }
).sort({ productCode: 1 });
~~~

This is the core benefit of **a single collection**: querying a unified product catalog requires no merging across multiple data sources.

### 5.2. Querying a Specific Variant

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  kind: "PHYSICAL",
  "details.weightGrams": { $gte: 500 }
});
~~~

For digital products:

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  kind: "DIGITAL",
  "details.licenseType": "PERSONAL"
});
~~~

For subscriptions:

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  kind: "SUBSCRIPTION",
  "details.billingInterval": "MONTH"
});
~~~

Filtering by **kind** establishes a clear contract: querying a variant-specific field is only meaningful for that variant. MongoDB can still query nested fields without specifying **kind**, yet including the variant makes code clearer and enables matching partial indexes.

### 5.3. Filtering on a Field Present in Only One Variant

~~~javascript
db.products.find({
  "details.assetId": { $exists: true }
});
~~~

**$exists: true** matches documents containing that field, even if its value is **null**. To exclude nulls, add an appropriate condition. Do not use **$exists** to infer product kind when **kind** is already the official discriminator.

### 5.4. Aggregating Statistics Grouped by kind

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      status: "ACTIVE"
    }
  },
  {
    $group: {
      _id: "$kind",
      numberOfProducts: { $sum: 1 }
    }
  },
  {
    $sort: { _id: 1 }
  }
]);
~~~

Illustrative output:

~~~javascript
[
  { _id: "DIGITAL", numberOfProducts: 1 },
  { _id: "PHYSICAL", numberOfProducts: 1 },
  { _id: "SUBSCRIPTION", numberOfProducts: 1 }
]
~~~

Never blindly sum **price.amount** across all variants and call it revenue: physical goods may price per unit, digital goods per license, and subscriptions per billing cycle. **Identical technical data types do not imply identical business units**.

### 5.5. Producing a Unified Display Field with `$switch`

~~~javascript
db.products.aggregate([
  { $match: { tenantId: "SHOP-A", status: "ACTIVE" } },
  {
    $project: {
      _id: 0,
      productCode: 1,
      name: 1,
      kind: 1,
      fulfillmentLabel: {
        $switch: {
          branches: [
            {
              case: { $eq: ["$kind", "PHYSICAL"] },
              then: "Requires shipping"
            },
            {
              case: { $eq: ["$kind", "DIGITAL"] },
              then: "Digital delivery"
            },
            {
              case: { $eq: ["$kind", "SUBSCRIPTION"] },
              then: "Recurring access"
            }
          ],
          default: "Unknown product kind"
        }
      }
    }
  }
]);
~~~

Aggregation can help normalize fields for presentation, though complex business rules and authorization checks still belong in the application/domain layer.

## 6. Setting Up Per-Variant Validators

MongoDB lets you attach **schema validation** to a collection via **$jsonSchema**. You can combine shared constraints with **oneOf** to ensure each document matches exactly one declared variant.

Example creating the collection from scratch (run only if **products** does not yet exist):

~~~javascript
use polymorphic_shop

db.createCollection("products", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "tenantId",
        "productCode",
        "kind",
        "name",
        "status",
        "price",
        "details",
        "schemaVersion"
      ],
      properties: {
        tenantId: { bsonType: "string" },
        productCode: { bsonType: "string" },
        kind: {
          enum: ["PHYSICAL", "DIGITAL", "SUBSCRIPTION"]
        },
        name: { bsonType: "string" },
        status: {
          enum: ["DRAFT", "ACTIVE", "ARCHIVED"]
        },
        schemaVersion: {
          bsonType: "int",
          minimum: 1
        },
        price: {
          bsonType: "object",
          required: ["amount", "currency"],
          properties: {
            amount: { bsonType: "decimal" },
            currency: { bsonType: "string" }
          }
        },
        details: { bsonType: "object" }
      },
      oneOf: [
        {
          properties: {
            kind: { enum: ["PHYSICAL"] },
            details: {
              bsonType: "object",
              required: [
                "inventorySku",
                "weightGrams",
                "shippingClass"
              ],
              properties: {
                inventorySku: { bsonType: "string" },
                weightGrams: { bsonType: "int", minimum: 1 },
                shippingClass: {
                  enum: ["STANDARD", "FRAGILE"]
                }
              }
            }
          }
        },
        {
          properties: {
            kind: { enum: ["DIGITAL"] },
            details: {
              bsonType: "object",
              required: [
                "assetId",
                "licenseType",
                "maxDownloads"
              ],
              properties: {
                assetId: { bsonType: "string" },
                licenseType: {
                  enum: ["PERSONAL", "TEAM"]
                },
                maxDownloads: { bsonType: "int", minimum: 1 }
              }
            }
          }
        },
        {
          properties: {
            kind: { enum: ["SUBSCRIPTION"] },
            details: {
              bsonType: "object",
              required: [
                "planCode",
                "billingInterval",
                "trialDays"
              ],
              properties: {
                planCode: { bsonType: "string" },
                billingInterval: { enum: ["MONTH", "YEAR"] },
                trialDays: { bsonType: "int", minimum: 0 }
              }
            }
          }
        }
      ]
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

**Reading the example rules:**

1. Every document must have the common fields, and price must be stored as BSON **Decimal128**.
2. **kind** must be within the declared enum set.
3. **oneOf** requires the document to match exactly one branch. Since each branch restricts **kind** differently, branches do not overlap.
4. For **PHYSICAL**, **details.weightGrams** must be BSON Int32 >= 1; other kinds enforce their own required field sets.
5. **validationAction: "error"** rejects writes violating the validator. **validationLevel: "strict"** applies checks to regular inserts and updates.

**Note:** the sample schema does not declare **additionalProperties: false**, so unforbidden extra fields are still permitted. To block unexpected fields, add constraints at the document/`details` level, bearing in mind overly strict locks can hinder schema evolution. Choose strictness based on business risk.

### 6.1. Combining Validators with Application Rules

JSON Schema validates **structure, types, enums, and certain value ranges**. It does not replace full business logic. For example:

- Does a warehouse SKU actually exist in the inventory service?
- Is a digital asset currently licensed for distribution?
- Is a subscription plan code valid for the current tenant and market?
- Does the VND price comply with rounding/tax policies?

These rules require external data and domain/service logic. Use MongoDB validators as a guardrail for **data shape**, combined with business enforcement in the application.

### 6.2. Do Not Tighten Production Validators While Ignoring Old Documents

When updating a validator with **collMod**, do not assume existing documents are automatically repaired. Previously invalid documents can remain stored and fail on subsequent updates. Before tightening a validator:

1. Audit stored data and classify existing shapes.
2. Define a migration path for non-compliant records.
3. Deploy code that reads both old and new formats.
4. Clean up legacy data in batches while monitoring errors.
5. Only after compliance is verified, tighten rules on the write path.

A validator **valid for new code** is not automatically compatible with historical data.

## 7. Indexes for Shared Queries and Variant-Specific Queries

A polymorphic collection can serve multiple query shapes. Design indexes from **actual query patterns**, not by indexing every field just because it exists.

### 7.1. Unique Index for Shared Business Identity

If within each tenant, **productCode** must be unique across all variants:

~~~javascript
db.products.createIndex(
  { tenantId: 1, productCode: 1 },
  { unique: true, name: "uq_tenant_product_code" }
);
~~~

This prevents SHOP-A from creating a PHYSICAL product and a DIGITAL product with the same **productCode**. A shared unique index is useful when variants truly share **one identity namespace**.

If the collection is **sharded**, unique indexes must satisfy shard-key constraints. Never assume any arbitrary index can be created or enforce cluster-wide uniqueness without checking the shard key.

### 7.2. Index for Shared Listings

~~~javascript
db.products.createIndex(
  { tenantId: 1, status: 1, productCode: 1 },
  { name: "ix_tenant_status_code" }
);
~~~

This index can serve queries filtering **tenantId**, **status**, and sorting by **productCode** from earlier examples. Verify actual benefit with **explain**, as the query planner depends on statistics, data distribution, and projections.

### 7.3. Compound Index for One Variant

~~~javascript
db.products.createIndex(
  {
    tenantId: 1,
    kind: 1,
    "details.weightGrams": 1
  },
  { name: "ix_physical_weight" }
);
~~~

Fits when physical items are frequently queried by weight. However, this index still stores entries for documents of other variants even when the weight field is absent. An alternative is a **partial index**.

### 7.4. Partial Index for One Variant

~~~javascript
db.products.createIndex(
  {
    tenantId: 1,
    "details.weightGrams": 1
  },
  {
    name: "ix_physical_weight_partial",
    partialFilterExpression: { kind: "PHYSICAL" }
  }
);
~~~

The index only includes documents matching **kind = PHYSICAL**. Applications should query **kind** explicitly:

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  kind: "PHYSICAL",
  "details.weightGrams": { $gte: 500 }
});
~~~

MongoDB only uses a partial index when the query filter guarantees index usage will not miss matching documents. Queries omitting the kind predicate will not benefit. Verify with:

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  kind: "PHYSICAL",
  "details.weightGrams": { $gte: 500 }
}).explain("executionStats");
~~~

### 7.5. Do Not Create Every Sample Index at Once in Production

The sample indexes above illustrate **alternative** options. Every index carries costs:

- Disk space and cache footprint;
- Index maintenance work on every write;
- Index build overhead on large collections;
- Ongoing monitoring and maintenance burden.

Measure real queries, inspect **explain**, and select a minimal sufficient index set. Do not create both a full compound index and an almost-overlapping partial index without evidence.

## 8. Mapping to Java: Representing Polymorphism in Code

In Java, polymorphism is commonly represented with interfaces, abstract classes, sealed interfaces, or concrete DTO sets. The key is **explicitly encoding the discriminator**, never guessing the subtype from field names.

### 8.1. A Domain Model Using Sealed Interfaces and Records

Java 21 example:

~~~java
public sealed interface ProductDetails
        permits PhysicalDetails, DigitalDetails, SubscriptionDetails {
}

public record PhysicalDetails(
        String inventorySku,
        int weightGrams,
        String shippingClass
) implements ProductDetails {
}

public record DigitalDetails(
        String assetId,
        String licenseType,
        int maxDownloads
) implements ProductDetails {
}

public record SubscriptionDetails(
        String planCode,
        String billingInterval,
        int trialDays
) implements ProductDetails {
}
~~~

These three **Details** types are explicit domain variants. A separate mapper translates MongoDB documents into the corresponding domain type.

### 8.2. Dispatching on the Discriminator with the Java Sync Driver

The snippet below illustrates mapping; assume the code has already retrieved an **org.bson.Document** from the collection:

~~~java
import org.bson.Document;

public final class ProductDetailsMapper {

    public static ProductDetails fromMongo(Document product) {
        String kind = product.getString("kind");
        Document details = product.get("details", Document.class);

        if (kind == null || details == null) {
            throw new IllegalArgumentException(
                    "Product kind and details are required"
            );
        }

        return switch (kind) {
            case "PHYSICAL" -> new PhysicalDetails(
                    details.getString("inventorySku"),
                    details.getInteger("weightGrams"),
                    details.getString("shippingClass")
            );
            case "DIGITAL" -> new DigitalDetails(
                    details.getString("assetId"),
                    details.getString("licenseType"),
                    details.getInteger("maxDownloads")
            );
            case "SUBSCRIPTION" -> new SubscriptionDetails(
                    details.getString("planCode"),
                    details.getString("billingInterval"),
                    details.getInteger("trialDays")
            );
            default -> throw new IllegalArgumentException(
                    "Unsupported product kind: " + kind
            );
        };
    }
}
~~~

A Java application reading from the same collection:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;

// database is pre-initialized via MongoClient.
MongoCollection<Document> products =
        database.getCollection("products");

Document stored = products.find(and(
        eq("tenantId", "SHOP-A"),
        eq("productCode", "EBOOK-MONGO-01")
)).first();

if (stored != null) {
    ProductDetails details = ProductDetailsMapper.fromMongo(stored);
    System.out.println(details);
}
~~~

The mapper above illustrates **branching explicitly on `kind`**, not a full production mapper: production code must also validate **schemaVersion**, exact types, nulls, enum values, tenant authorization, and error handling. Java's **getInteger** does not automatically carry **Decimal128** or **Int64** semantics; preserve the exact Java/BSON type for each field.

### 8.3. Using Spring Data MongoDB

In Spring Data, you can choose:

1. A shared **document persistence model** containing **kind** and **details**, then manually map to domain variants.
2. A **class hierarchy** using Spring Data MongoDB's type metadata (such as **_class** or type aliases) so converters instantiate subtypes.
3. A **custom converter** or specialized mapping mechanism to avoid coupling stored documents to Java class names/type hints.

Example shared persistence model:

~~~java
import org.bson.Document;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;

@org.springframework.data.mongodb.core.mapping.Document(
        collection = "products"
)
public class ProductDocument {
    @Id
    private ObjectId id;

    private String tenantId;
    private String productCode;
    private String kind;
    private String name;
    private Document details;
    private int schemaVersion;

    // Constructor, getters, setters...
}
~~~

This is a **sketch** of a persistence model; a real application adds **price**, **status**, and **createdAt** per the data contract, along with field checks and converters.

**Note on `_class`:** Spring Data type metadata helps deserialize subtypes inside Spring Data, yet Java class names should not serve as the **stable business discriminator** when data is shared with Node.js, Python, batch jobs, and other services. The **kind** field should act as a language-neutral contract when data crosses service boundaries.

### 8.4. Avoid "Guessing" Mappers

Avoid:

~~~java
// Do not infer the variant solely from field presence.
if (details.containsKey("weightGrams")) {
    // assume PHYSICAL
} else if (details.containsKey("assetId")) {
    // assume DIGITAL
} else {
    // assume SUBSCRIPTION
}
~~~

When schemas add new fields or a document is malformed, guessing silently instantiates the wrong subtype. **kind** must be cross-checked against payload and validators. Handle unsupported kinds with an explicit policy (reject, preserve raw payload for backward compatibility, or dead-letter), never defaulting to an arbitrary variant.

## 9. Updating Polymorphic Documents and Preserving Invariants

### 9.1. Updating Common Fields

~~~javascript
db.products.updateOne(
  {
    tenantId: "SHOP-A",
    productCode: "EBOOK-MONGO-01",
    status: "ACTIVE"
  },
  {
    $set: {
      name: "MongoDB E-book, Second Edition"
    }
  }
);
~~~

MongoDB guarantees **single-document atomicity** for appropriate update operations. Updating both common fields and variant fields in the same document does not require a multi-document transaction for atomicity.

### 9.2. Updating a Variant-Specific Field

~~~javascript
db.products.updateOne(
  {
    tenantId: "SHOP-A",
    productCode: "EBOOK-MONGO-01",
    kind: "DIGITAL"
  },
  {
    $set: {
      "details.maxDownloads": NumberInt(5)
    }
  }
);
~~~

The **kind: "DIGITAL"** predicate prevents accidentally setting **maxDownloads** on a PHYSICAL product with the same **productCode** (or a malformed document).

### 9.3. Should You Change `kind` In Place?

Example:

~~~javascript
// Warning: changing only the discriminator is not enough.
db.products.updateOne(
  { productCode: "KEYBOARD-01" },
  { $set: { kind: "DIGITAL" } }
);
~~~

This leaves the document self-contradictory: `kind` is DIGITAL while **details** still holds weight/warehouse fields. The **oneOf** validator will reject it for missing required DIGITAL fields.

If business logic genuinely permits changing variant types, update **kind** and the entire new payload **in one atomic operation**, while also handling downstream impacts on inventory, fulfillment, entitlements, and external links. In many domains, **changing product nature** is better modeled as creating a new product/version rather than mutating a single field.

### 9.4. Controlling Concurrent Updates

If two requests edit the same document, atomicity alone does not prevent business-level **lost updates**. Use optimistic locking with a dedicated **version** field:

~~~javascript
db.products.updateOne(
  {
    tenantId: "SHOP-A",
    productCode: "EBOOK-MONGO-01",
    revision: NumberInt(3)
  },
  {
    $set: { "details.maxDownloads": NumberInt(10) },
    $inc: { revision: 1 }
  }
);
~~~

This conditional update requires the document to **currently have revision = 3**. Code must check **matchedCount** to tell whether the update succeeded or hit a conflict and respond accordingly. **revision** for write concurrency control differs in meaning from **schemaVersion**, which tracks data structure versions.

## 10. Schema Evolution as Variants Grow

One advantage of the document model is adding variants without adding dozens of null columns to existing documents. However, this **does not eliminate migration and compatibility requirements**.

### 10.1. Example Adding a New Variant

Suppose the system adds **BUNDLE** (multi-product package) with **details.items** containing codes and quantities. Changes to evaluate:

- Do APIs/DTOs and domain models accept **kind = BUNDLE**?
- Does the MongoDB **validator** include the BUNDLE branch?
- Do UI screens, reports, ordering, and fulfillment handle the new kind?
- Are new indexes needed for BUNDLE queries?
- What will legacy consumers do upon encountering an unknown kind?

Adding a **BUNDLE** document while legacy code falls back to **default -> SUBSCRIPTION** causes misinterpretation. Adding a variant is a **business contract change**, even though the database requires no `ALTER TABLE`.

### 10.2. Example Schema Versioning for DIGITAL

Version 1:

~~~javascript
{
  kind: "DIGITAL",
  schemaVersion: NumberInt(1),
  details: {
    assetId: "ASSET-MONGO-PDF",
    licenseType: "PERSONAL",
    maxDownloads: NumberInt(3)
  }
}
~~~

Version 2 adds **deliveryMethod**:

~~~javascript
{
  kind: "DIGITAL",
  schemaVersion: NumberInt(2),
  details: {
    assetId: "ASSET-MONGO-PDF",
    licenseType: "PERSONAL",
    maxDownloads: NumberInt(3),
    deliveryMethod: "SECURE_LINK"
  }
}
~~~

A safe rollout plan:

1. **Read both v1 and v2:** new code accepts old documents and applies defined behavior when **deliveryMethod** is absent.
2. **Write v2 for new documents:** older code may not understand v2 yet, so sequence consumer upgrades first.
3. **Migrate legacy data in batches:** update documents with clear version/marker filters.
4. **Monitor progress:** count remaining documents per `schemaVersion`.
5. **Tighten the validator and drop v1 read paths** once all dependents are ready.

Illustrative migration after code and validators support the new schema:

~~~javascript
db.products.updateMany(
  {
    kind: "DIGITAL",
    schemaVersion: NumberInt(1),
    "details.deliveryMethod": { $exists: false }
  },
  {
    $set: {
      schemaVersion: NumberInt(2),
      "details.deliveryMethod": "SECURE_LINK"
    }
  }
);
~~~

In production, verify tenant scoping, batch sizes, rollback plans, concurrent writes, and auditing before running broad migrations. If some documents have different semantics (e.g., ineligible for secure links), never backfill an unfounded default.

### 10.3. Schema Version Does Not Have to Increment on Every Field Addition

If adding a backward-compatible **optional** field, some teams keep the same version. When changing meaning or structure in ways older consumers cannot interpret, incrementing the version expresses the compatibility boundary. Maintain consistent organization-wide rules rather than treating version like a deployment counter.

## 11. Choosing Collection Boundaries Based on Access Patterns

MongoDB encourages modeling around **workloads and access patterns**. Polymorphic documents fit when variants are genuinely accessed as a unified entity set, but become costly when unrelated domains are forced into one collection.

| Factor | Single Polymorphic Collection | Separate Collections per Variant |
|---|---|---|
| Shared listings/search | Convenient; one unified query and index. | Must merge results across multiple sources. |
| Cross-type identity | Can enforce with a shared unique index. | Needs external mechanisms to enforce uniqueness across collections. |
| Schema validation | Uses `oneOf`/`anyOf` branching on `kind`. | Per-collection validators are usually simpler. |
| Specialized indexes | Can use compound/partial indexes, requiring balance. | Each collection manages indexes independently. |
| Scale/growth rate | Multiple workloads share resources in one collection. | Easier to isolate operations, retention, and workload per type. |
| Permissions/retention | Enforced in application filters; some policies harder to split. | Permissions and lifecycles split cleanly per collection. |
| Adding a new variant | Must update discriminator, schema, consumers. | Can add a new collection, though aggregate queries must adapt. |
| Joint common + variant updates | Single document updates atomically. | Spanning collections may require transactions. |

### 11.1. When to Keep in One Collection?

For example, an e-commerce platform with a unified **Catalog** page, shared search, shared pricing, and unified selling statuses. PHYSICAL/DIGITAL/SUBSCRIPTION variants are all treated as **Product**. Using a single **products** collection is natural if each variant's details stay compact.

### 11.2. When to Separate Collections?

For instance, **audit logs**, **billing invoices**, and **catalog products** share fields like `tenantId`, `createdAt`, and `status`, yet represent completely distinct business concepts. Never lump them into one collection merely because they share those fields.

Even within the same concept, one variant might experience massive write volume, short retention, or sensitive data isolation requirements. If every API for that variant takes its own separate path, the benefit of a shared collection diminishes.

## 12. Polymorphism and Business Event Modeling

Another common case beyond products is **business events**. Consider an **order_events** collection with variants:

~~~javascript
{
  eventId: "EV-1001",
  aggregateId: "ORDER-9001",
  eventType: "ORDER_CREATED",
  occurredAt: ISODate("2026-02-01T10:00:00Z"),
  payload: {
    customerId: "CUS-01",
    totalAmount: NumberDecimal("320000.00")
  },
  schemaVersion: NumberInt(1)
}
~~~

~~~javascript
{
  eventId: "EV-1002",
  aggregateId: "ORDER-9001",
  eventType: "PAYMENT_CAPTURED",
  occurredAt: ISODate("2026-02-01T10:05:00Z"),
  payload: {
    paymentId: "PAY-01",
    capturedAmount: NumberDecimal("320000.00")
  },
  schemaVersion: NumberInt(1)
}
~~~

Here **eventType** is the discriminator. Events share common metadata while each **payload** differs. This pattern stores and reads heterogeneous event histories from one stream.

However, distinguish:

- **Polymorphic entity document:** represents the current state of a product/order.
- **Polymorphic event document:** represents an immutable fact that occurred at a point in time.

Events typically require immutability, ordering, idempotency, and distinct retention rules. Do not treat event documents and current-state documents identically merely because both use discriminators.

## 13. Polymorphism in Multi-Tenant Systems and Sharded Clusters

If every document includes **tenantId**, APIs should scope operations to the current tenant:

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  kind: "DIGITAL"
});
~~~

Never trust client-supplied `tenantId` blindly; the server must derive the tenant from authenticated/authorized context and enforce access checks.

In a sharded cluster, choose the **shard key** based on data distribution, queries, and real load. Even though every document has **kind**, the shard key does not have to include **kind**. If one product type accounts for most writes, partitioning solely by `kind` can cause hotspots or skewed distribution.

Considerations:

1. **Common fields** like `tenantId`/`productCode` typically serve multi-variant queries better than variant-only fields.
2. **Unique indexes** on sharded collections must comply with shard-key rules; verify before promising cluster-wide uniqueness.
3. **Partial indexes** and variant-specific indexes must match query planner requirements; never assume every sharding/index combination works seamlessly.
4. One oversized tenant or variant can skew workload even across many shards.
5. Sharding does not cure an oversized document or an unbounded array.

Shard key decisions are expensive to change, so evaluate them using measured data and queries rather than Java class hierarchies.

## 14. Common Design Mistakes

### 14.1. No Explicit Discriminator

Checking only field existence makes it hard to tell malformed documents from valid variants. **Fix:** use an explicit enum **kind** and bind shapes via validator rules.

### 14.2. Overusing Null Values

Documents carrying dozens of fields meaningful only to other types are hard to maintain. **Fix:** group variant fields inside a variant payload or split collections if divergence is extreme.

### 14.3. Treating Missing Fields as Valid Implicit Defaults

A missing **trialDays** does not automatically mean 0; a missing **maxDownloads** does not automatically mean unlimited. Defaults must be **explicit business rules**, versioned if necessary.

### 14.4. Mismatched `kind` and Payload

For instance, **kind = DIGITAL** while holding **weightGrams**. **Fix:** per-variant validators, fail-fast mappers, and pre-write input checks.

### 14.5. Changing `kind` Without Migrating Data

Changing **kind** while leaving old payload fields behind breaks invariants. **Fix:** treat variant conversion as a full business operation, not a single-field patch.

### 14.6. Aggregating Across Incompatible Units

A physical item's price and a monthly subscription price are both decimals, yet summing them as identical units can be meaningless. **Fix:** normalize domain metrics and group by `kind`/`billingInterval` before reporting.

### 14.7. Using Java Class Metadata as a Cross-Service Contract

If the discriminator is only a class name in **_class**, renaming a package or adding a non-Java service creates brittle coupling. **Fix:** use a stable business **kind** code when data crosses technology boundaries.

### 14.8. Document Bloat from Embedding Unbounded History

Unbounded **history**, **downloads**, or **events** arrays inflate documents and degrade updates. **Fix:** move unbounded histories to separate collections while keeping aggregate-scoped data in the document.

### 14.9. Failing to Plan for Unknown Variants

Legacy consumers may encounter a new `kind` after a deployment. **Fix:** roll out backward-compatibly, handle unknown kinds and migrations explicitly, and never coerce into an arbitrary default subtype.

### 14.10. Indexing Every Field of Every Variant

Excessive indexes inflate write overhead and storage. **Fix:** base indexes on real query patterns, use compound/partial indexes appropriately, and inspect **explain**.

## 15. Practice Lab: Building a Polymorphic Catalog

The goal is practicing architecture, queries, and data guards on a dedicated lab database.

### Step 1 — Create Collection with Polymorphic Records

In `mongosh`, switch to **polymorphic_shop** and run the **insertMany** example from Section 3. You may create the **validator** from Section 6 before inserting; if the collection already exists, use a fresh test database/collection or **collMod**.

### Step 2 — Query All Product Types

~~~javascript
db.products.find(
  { tenantId: "SHOP-A", status: "ACTIVE" },
  { _id: 0, productCode: 1, kind: 1, name: 1 }
);
~~~

Expect all three product types, distinguished by **kind**.

### Step 3 — Query Only Digital Products

~~~javascript
db.products.find(
  { tenantId: "SHOP-A", kind: "DIGITAL" },
  { _id: 0, productCode: 1, "details.assetId": 1 }
);
~~~

Results need only the fields specific to the DIGITAL variant.

### Step 4 — Inspect BSON Types

~~~javascript
db.products.aggregate([
  {
    $project: {
      _id: 0,
      kind: 1,
      amountType: { $type: "$price.amount" },
      weightType: { $type: "$details.weightGrams" },
      maxDownloadsType: { $type: "$details.maxDownloads" }
    }
  }
]);
~~~

A field absent in a variant evaluates to **missing** under the aggregation `$type` operator. This confirms the collection holds multiple shapes while shared fields keep uniform types.

### Step 5 — Test a Malformed Variant Document

If the validator from Section 6 is active, try:

~~~javascript
db.products.insertOne({
  tenantId: "SHOP-A",
  productCode: "INVALID-01",
  kind: "DIGITAL",
  name: "Invalid digital product",
  status: "ACTIVE",
  price: {
    amount: NumberDecimal("100.00"),
    currency: "VND"
  },
  details: {
    weightGrams: NumberInt(500)
  },
  schemaVersion: NumberInt(1)
});
~~~

The document declares `kind: "DIGITAL"` yet lacks **assetId**, **licenseType**, and **maxDownloads**. Under **strict/error** validation, MongoDB rejects the write.

### Step 6 — Inspect Indexes Before Deciding

Create an index matching a lab query:

~~~javascript
db.products.createIndex(
  { tenantId: 1, status: 1, productCode: 1 }
);

db.products.find({
  tenantId: "SHOP-A",
  status: "ACTIVE"
}).sort({ productCode: 1 }).explain("executionStats");
~~~

On tiny datasets, MongoDB may select a **collection scan** or another plan due to negligible cost; do not judge an index as good or bad from a handful of records. Understand the query shape first, then evaluate on a representative workload.

### Step 7 — Design a New Variant on Paper

Design a **SERVICE** variant with **durationMinutes**, **serviceLocationType**, and **bookingWindowDays**. Determine:

- Identity, common fields, and variant fields;
- Discriminator value;
- Validator branch to add;
- How the Java mapper instantiates the subtype;
- Required queries and indexes;
- Compatibility with consumers unaware of SERVICE;
- Whether SERVICE truly belongs in the **products** collection.

This is a domain design exercise—no need to rush inserting production documents.

## 16. Review Questions

1. Why can structurally different documents coexist validly in one MongoDB collection?
2. How does the **Polymorphic Pattern** differ from uncontrolled **schema drift** in a collection?
3. How do the roles of **kind**, **schemaVersion**, and **status** differ?
4. Why group variant attributes inside **details** in the catalog example? When is that unnecessary?
5. What does a **oneOf** validator enforce when a collection holds three product kinds?
6. What benefit does a **partial index** filtered by `kind` provide, and why might a query omitting `kind` fail to use it?
7. When Java code receives an unsupported **kind**, what can go wrong if the mapper's **default** branch returns an arbitrary subtype?
8. Why should you not casually change `kind` from PHYSICAL to DIGITAL with a simple **$set** command?
9. In what situations should variants be split into separate collections?
10. Why can **price.amount** still not be summed meaningfully across PHYSICAL and SUBSCRIPTION even though both use `Decimal128`?
11. When adding a BUNDLE variant, which components beyond storage layout must be updated?
12. How does MongoDB's single-document atomicity help when updating a product with both common and variant fields?

## 17. Key Takeaways for Representing Business Variants

A polymorphic document model works well when:

1. **Shared identity/lifecycle:** variants are genuinely forms of the same business concept.
2. **Explicit discriminator:** `kind` uses stable values rather than inference from field or class names.
3. **Consistent shared invariants:** common fields keep uniform structure and semantics.
4. **Bounded variant payload:** variant fields are cleanly organized, e.g., inside **details**.
5. **Kind-aware validation and mapping:** malformed shapes fail fast.
6. **Workload-aligned queries/indexes:** separate shared queries from variant-specific queries.
7. **Planned schema evolution:** legacy consumers, migrations, and validators coordinate via versioning.
8. **Bounded document size:** split unbounded histories/arrays and non-co-read data out of the aggregate.

~~~text
                    Business concept: Product
                                |
                Common identity / common fields
                                |
                    Discriminator: kind
                                |
             +------------------+------------------+
             |                  |                  |
          PHYSICAL            DIGITAL         SUBSCRIPTION
             |                  |                  |
          details             details            details
       shipping/stock      asset/license      plan/billing
             |                  |                  |
             +------------------+------------------+
                                |
                   Shared products collection
                                |
                   Validation + indexes + mapper
~~~

**Polymorphic documents are not simply "MongoDB lets you put different fields in a collection."** The pattern's value comes from unifying related variants under shared identity and access patterns while keeping variant differences under a controllable data contract.

### Further MongoDB Reading

- [Polymorphic Data Pattern](https://www.mongodb.com/docs/manual/data-modeling/design-patterns/polymorphic-data/polymorphic-schema-pattern/) — use cases for polymorphic data.
- [Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/) — workload-driven document modeling.
- [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — enforcing constraints alongside flexible schemas.
- [Specify JSON Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/specify-json-schema/) — using **$jsonSchema**.
- [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/) — indexing only documents matching a filter.
- [MongoDB Java Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — mapping, reading, and writing documents in Java.

When building a Java or Spring Boot module backed by MongoDB, start from **business semantics and access patterns**, then decide which variants belong to the same aggregate and collection. Java classes, schema validation, and indexes should reflect that decision—rather than starting from existing class hierarchies and forcing MongoDB to mimic them.
