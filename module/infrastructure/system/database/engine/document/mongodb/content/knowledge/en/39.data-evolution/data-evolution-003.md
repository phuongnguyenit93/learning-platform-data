# Reading Multi-Version Data and Transforming on Read in MongoDB

## 1. The Problem: One Collection, Multiple Document Shapes

A rental listing service running on MongoDB has operated for years. Over that time, the development team kept evolving requirements:

- Initially, rent was stored as an integer VND amount in the **rent_vnd** field.
- Later, **monthly_rent_vnd** was stored as BSON Decimal128 to represent decimal precision explicitly.
- In the latest version, rent is embedded under **pricing.monthly**, along with currency.
- Location changed sequentially from **city** to **location.city_code** and then **address.city_code**.
- The boolean active flag was replaced by the publication status **PUBLISHED/DRAFT**.

MongoDB allows documents within the same collection to have different field names and structures. Consequently, after three releases, the collection can simultaneously hold:

~~~text
Collection rental_listings_425
  |
  +-- Document A: schema v1 (no schema_version)
  |      rent_vnd: Int64
  |      city: "HCM"
  |      active: true
  |
  +-- Document B: schema v2
  |      monthly_rent_vnd: Decimal128
  |      location.city_code: "HCM"
  |      status: "PUBLISHED"
  |
  +-- Document C: schema v3
         pricing.monthly.amount: Decimal128
         pricing.monthly.currency: "VND"
         address.city_code: "HCM"
         publication.status: "PUBLISHED"
~~~

Meanwhile, the API wants to return a unified DTO:

~~~json
{
  "id": "b425-v1",
  "title": "Studio near the park",
  "cityCode": "HCM",
  "monthlyRent": {
    "amount": "12500000.00",
    "currency": "VND"
  },
  "status": "PUBLISHED",
  "publishedAt": "2026-01-15T09:00:00Z"
}
~~~

The core idea is **reading multi-version data and transforming on read** (*schema-on-read transformation*). Read the legacy document, determine its version, validate data types, and convert it into a canonical model understood by the current application; you do not necessarily have to rewrite millions of documents on deployment day.

~~~text
   MongoDB collection holding v1 / v2 / v3
                  |
                  v
       Read raw BSON document
                  |
                  v
       Determine schema version
                  |
          +-------+-------+
          |       |       |
         v1      v2      v3
          |       |       |
      Adapter1 Adapter2 Adapter3
          |       |       |
          +-------+-------+
                  |
                  v
          Canonical ListingView
                  |
                  v
             API response
~~~

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish between **schema version**, **document revision**, **application version**, and **MongoDB server version**.
2. Establish contracts for multiple coexisting BSON document shapes.
3. Design a **canonical read model** and per-version adapters/upcasters.
4. Carefully handle **missing fields, null fields, wrong BSON types, Decimal128, dates/times, enums, and ambiguous values**.
5. Implement multi-version reads using **mongosh**, the **Java MongoDB driver**, or **Spring Data MongoDB**.
6. Build queries and indexes covering **different field paths** during transition.
7. Differentiate transformations **in the application**, **in an aggregation pipeline**, and via **write-back read-repair**.
8. Avoid losing concurrent updates during lazy write-back using **compare-and-set** or version guards.
9. Roll out changes via **expand–migrate–contract** and rolling deployments.
10. Test compatibility, measure version ratios, read errors, and long-term processing costs.

> **Scope and safety:** This lesson belongs to **Database Engine Document MongoDB → Data Evolution**. Examples use only the **mongo_evolution_lab_425** database and **rental_listings_425** collection, with fixed `_id`s and `labTag`. Default reads do not mutate documents; all write-back examples are clearly marked and must only run in an isolated lab. Java/Spring Data, converter, and aggregation behaviors must be tested against your exact versions.

## 2. Why Does One Collection End Up with Multiple Schemas?

### 2.1. MongoDB Does Not Force Every Document to Have Identical Fields

MongoDB stores BSON documents. Without an appropriate **server-side schema validation** rule, an application can insert:

~~~javascript
{ _id: "x1", rent_vnd: NumberLong("12500000") }
~~~

and:

~~~javascript
{
  _id: "x2",
  pricing: {
    monthly: {
      amount: NumberDecimal("12500000.00"),
      currency: "VND"
    }
  }
}
~~~

into the same collection.

This helps when evolving schemas incrementally, yet the application must know how to interpret the data. **Flexible schema does not mean data needs no contract.**

### 2.2. Deploying Code Does Not Automatically Migrate Documents

Suppose a Spring Data entity changes:

~~~java
// Old version:
@Field("rent_vnd")
private Long monthlyRent;

// New version:
@Field("monthly_rent_vnd")
private BigDecimal monthlyRent;
~~~

When the new class is deployed, MongoDB **does not rename fields inside old documents**. If the new converter only reads `monthly_rent_vnd`, the Java property will be `null` even though the document still holds `rent_vnd`.

### 2.3. Rolling Deployments Produce Multiple Writer Versions

In a multi-pod deployment:

~~~text
09:00  Pod A is running app v2
09:01  Pod B switches to app v3
09:03  Pod C is still running app v2
09:05  All pods are on app v3
~~~

Between 09:01 and 09:05, the system can simultaneously have:

- App v2 writing schema v2.
- App v3 writing schema v3.
- Legacy v1/v2 documents not yet backfilled.

The new application must **read remaining old data**, while the old application must not break on documents written by the new version if it can still encounter them.

### 2.4. Other Sources of Mixed Schemas

Beyond rolling deployments, there are:

- Batch imports from legacy systems.
- Offline mobile clients submitting old payloads.
- Message consumers running different versions.
- Replication/migrations from another datastore.
- Manual scripts or operational jobs.
- Incomplete backfills halted after a mid-run failure.
- Restores from backups taken prior to migration.

Therefore, never assume that “app v3 is deployed” means every document conforms to schema v3.

## 3. Four Version Concepts to Keep Separate

| Concept | Example | Meaning |
| --- | --- | --- |
| **Schema version** | schema_version: 3 | Document shape and field semantics |
| **Document revision** | revision: 17 | Mutation count or optimistic-lock token for a document |
| **Application version** | listing-service 4.8.2 | Version of the reading/writing program |
| **MongoDB server version** | MongoDB 8.x | Engine/API version, distinct from schema contract |

### 3.1. `schema_version`

Example:

~~~javascript
{
  _id: "b425-v3",
  schema_version: 3,
  pricing: {
    monthly: {
      amount: NumberDecimal("12500000.00"),
      currency: "VND"
    }
  }
}
~~~

`schema_version` is **application-defined metadata**, not a mandatory MongoDB built-in field. Name it consistently and document it in a schema catalog.

### 3.2. `revision`

~~~javascript
{
  _id: "b425-v3",
  schema_version: 3,
  revision: NumberLong("17")
}
~~~

`revision` serves as a **concurrency token** if all writers obey optimistic locking rules. Upgrading schema v2 → v3 may bump `revision` once, whereas `schema_version` **does not increment on every title or rent edit**.

### 3.3. App Version

App v5 may keep reading schema v1/v2/v3 for years. Conversely, app v3 should not blindly assume it can read schema v4 before an adapter for v4 is implemented.

### 3.4. Avoid Ambiguous `version` Fields

If a document contains:

~~~javascript
{ version: 8 }
~~~

readers cannot tell whether that is a schema version or an optimistic-lock counter. Use clear names like **schema_version** and **revision**, paired with explicit field types and invariants.

## 4. Three-Schema Contract Used Throughout This Lesson

We use a single collection **rental_listings_425** and three generations of contracts.

### 4.1. Schema v1 — Legacy Without Version Marker

~~~javascript
{
  _id: "b425-v1",
  labTag: "evolution425-v1",
  tenant_id: "tenant-001",
  title: "Studio near the park",
  rent_vnd: NumberLong("12500000"),
  city: "HCM",
  active: true,
  created_at: ISODate("2026-01-15T09:00:00Z")
}
~~~

v1 conventions:

- **No schema_version**: treated as v1 **only because a verified historical contract exists**.
- `rent_vnd` is integer VND, not millions of VND and not cents.
- `active=true` means the listing is published.
- `created_at` was used by the legacy system as publication time per this example's business contract.

If a real system used `created_at` as draft creation time, **never arbitrarily turn it into `publishedAt`** just to fill a field in the new API.

### 4.2. Schema v2 — Renamed Fields, Still Fairly Flat

~~~javascript
{
  _id: "b425-v2",
  labTag: "evolution425-v1",
  schema_version: 2,
  tenant_id: "tenant-001",
  title: "Apartment with balcony",
  monthly_rent_vnd: NumberDecimal("15000000.00"),
  location: {
    city_code: "HCM"
  },
  status: "PUBLISHED",
  published_at: ISODate("2026-01-16T09:00:00Z")
}
~~~

v2 conventions:

- `schema_version` is BSON integer 2.
- Rent is BSON Decimal128.
- City lives under **location.city_code**.
- `status` is string enum **PUBLISHED** or **DRAFT**.
- `published_at` is BSON Date.

### 4.3. Schema v3 — Nested Pricing and Publication

~~~javascript
{
  _id: "b425-v3",
  labTag: "evolution425-v1",
  schema_version: 3,
  tenant_id: "tenant-001",
  title: "Three-bedroom townhouse",
  pricing: {
    monthly: {
      amount: NumberDecimal("23000000.00"),
      currency: "VND"
    }
  },
  address: {
    city_code: "HN"
  },
  publication: {
    status: "PUBLISHED",
    published_at: ISODate("2026-01-17T09:00:00Z")
  }
}
~~~

v3 conventions:

- Explicit currency, e.g., VND.
- Rent is embedded.
- City lives under **address.city_code**.
- Status and `publishedAt` live under **publication**.

### 4.4. Comparison Table

| Business Meaning | v1 | v2 | v3 |
| --- | --- | --- | --- |
| Version | No marker | schema_version = 2 | schema_version = 3 |
| ID | `_id` String | `_id` String | `_id` String |
| Tenant | `tenant_id` | `tenant_id` | `tenant_id` |
| Title | `title` | `title` | `title` |
| Amount | `rent_vnd` Int64 | `monthly_rent_vnd` Decimal128 | `pricing.monthly.amount` Decimal128 |
| Currency | Implicit VND | Implicit VND | `pricing.monthly.currency` |
| City | `city` | `location.city_code` | `address.city_code` |
| Status | `active` Boolean | `status` String | `publication.status` String |
| Publish Date | `created_at` Date | `published_at` Date | `publication.published_at` Date |

### 4.5. Normalization Rules Must Be Business-Valid

Examples of **approved** conversions:

~~~text
v1 rent_vnd: Int64 12500000
          -> Money(12500000.00, "VND")

v1 active: true
          -> PublicationStatus.PUBLISHED

v1 active: false
          -> PublicationStatus.DRAFT
          (only if legacy contract confirms false means DRAFT)
~~~

If v1 `active=false` also covered “deleted” or “suspended,” mapping everything to DRAFT **loses business meaning**. You would need historical fields, a distinct state like UNKNOWN, or manual triage.

## 5. Canonical Read Model: A Unified Interpretation

### 5.1. Do Not Force Every Layer to Read Raw BSON

If business services repeatedly write:

~~~java
if (document.containsKey("rent_vnd")) {
    // legacy
} else if (document.containsKey("monthly_rent_vnd")) {
    // v2
} else {
    // v3
}
~~~

across dozens of endpoints, version logic duplicates and becomes fragile. It is better to build **a single compatibility boundary**:

~~~text
MongoDB BSON v1/v2/v3
       |
       v
VersionedListingReader
       |
       v
ListingView (canonical)
       |
       +--> Search API
       +--> Rental pricing view
       +--> Recommendation service
       +--> Reporting
~~~

### 5.2. Java Read Model

Assuming Java 17+:

~~~java
package com.example.mongo425.domain;

import java.math.BigDecimal;
import java.time.Instant;

public record Money(
    BigDecimal amount,
    String currency
) {}

public enum PublicationStatus {
    PUBLISHED,
    DRAFT
}

public record ListingView(
    String id,
    String tenantId,
    String title,
    Money monthlyRent,
    String cityCode,
    PublicationStatus status,
    Instant publishedAt
) {}
~~~

In Java, each top-level public type belongs in its own file matching its type name; the blocks above illustrate **Money.java**, **PublicationStatus.java**, and **ListingView.java**.

### 5.3. Invariants of `ListingView`

A valid `ListingView` for this lesson's API:

- `id` and `tenantId` are non-blank Strings.
- `title` is non-blank.
- `monthlyRent.amount` is a non-negative BigDecimal.
- `currency` is **VND** across all three example schemas.
- `cityCode` belongs to the business-allowed set (HCM, HN, DN in the lab).
- `status` is a known enum value.
- `publishedAt` is a valid `Instant`.

If the canonical view cannot be constructed without guessing, the reader should **fail in a controlled manner** rather than returning a corrupt object or defaulting rent to 0.

### 5.4. Canonical Read Model vs. Canonical Stored Schema

The read model is the **in-memory post-transformation representation**. MongoDB can still retain v1/v2/v3:

~~~text
Read transformation:
  BSON v1 -> ListingView
  BSON v2 -> ListingView
  BSON v3 -> ListingView

Without writes:
  MongoDB keeps BSON v1/v2/v3 unchanged
~~~

Only when the application runs an explicit write-back or migration does stored data change.

## 6. Detecting Document Version

### 6.1. Explicit Marker

For v2/v3:

~~~javascript
{ schema_version: 2 }
{ schema_version: 3 }
~~~

The reader can dispatch directly:

~~~text
schema_version == 2 -> V2Adapter
schema_version == 3 -> V3Adapter
~~~

### 6.2. Missing Marker in Historical Data

In this example, **absent `schema_version`** means schema v1 because the team verified that all legacy documents prior to migration day lacked a marker and followed the v1 contract.

Never apply this rule blindly to imported or corrupted data.

### 6.3. Missing Differs from Null

~~~javascript
{ _id: "a" }                        // field missing
{ _id: "b", schema_version: null }   // explicit null
{ _id: "c", schema_version: "2" }    // wrong type string
{ _id: "d", schema_version: 2 }      // valid
~~~

**Never treat `null` or string `"2"` as v2.** If you want to support them, document the contract and test separately; by default, flag such documents as malformed.

In `mongosh`:

~~~javascript
db.rental_listings_425.find({
  schema_version: { $exists: false }
});
~~~

finds missing markers more accurately than:

~~~javascript
db.rental_listings_425.find({
  schema_version: null
});
~~~

because equality with `null` matches both explicit `null` and missing fields.

### 6.4. Future Versions

If a document has:

~~~javascript
{ schema_version: 4 }
~~~

while the application only knows up to v3:

- **Do not** silently downgrade v4 to v3.
- **Do not** drop unknown fields and re-save as v3.
- Throw **UnsupportedSchemaVersion** with PII-scrubbed context.
- Emit metrics/alerts and handle via compatibility policy.

This is critical during rolling deployments or when older apps still encounter documents written by newer releases.

### 6.5. Version Is a Contract, Not Just a Number

Schema v3 does not imply every v3 document is valid. A document with `schema_version:3` missing `pricing.monthly.amount` is still broken. Readers must validate both **structure and semantics** per version.

## 7. Transformation-on-Read Strategies

| Strategy | Where Transformation Runs | Writes Back to DB? | When Appropriate |
| --- | --- | --- | --- |
| **Application adapter** | Java service/repository boundary | No | Rich business rules, strict validation needed |
| **Custom Spring converter** | MappingMongoConverter | No by default | Deep integration into mapping layer |
| **Aggregation projection** | MongoDB query pipeline | No, unless `$merge`/`$out` | Reporting/search projection, reduces BSON transfer |
| **Read-through cache normalize** | Cache/load layer | Usually no source DB write | Multiple readers share canonical cache |
| **Lazy read-repair** | Reader reads and writes back new shape | Yes | Gradual legacy data reduction with guardrails |
| **Offline backfill** | Batch migration job | Yes | Canonicalizing entire collection independent of reads |

There is no single universally best option. An application adapter is clearest when conversions carry business semantics; aggregation helps when filtering/grouping across multiple paths; offline migration is needed when you do not want to maintain multiple adapters forever.

### 7.1. Per-Version Adapters

Pros:

- Version-specific contracts live in one place.
- Easy to unit test with BSON fixtures.
- Accurately flags malformed data.
- Never mutates the database during reads.

Cons:

- Each read pays conversion cost.
- Must maintain code for multiple versions.
- MongoDB-level queries/indexes still must handle different field paths.

### 7.2. Upcaster Chain

Another organization style:

~~~text
Raw v1 -> upcast v1 to v2 -> upcast v2 to v3
Raw v2 --------------------> upcast v2 to v3
Raw v3 ------------------------------------> canonical
~~~

Its benefit is reusing transformation steps. Caveats:

- Every step needs a strict contract.
- A bug in one step affects all older versions.
- Intermediate versions might require fields absent from earlier schemas.
- Both individual steps and full chains must be tested.

When only three markedly different schemas exist, direct v1/v2/v3 → canonical adapters are often simpler.

### 7.3. Projections and Read Models Are Not Writer Schemas

Readers can transform v1 into `ListingView`, while new writers should have **one official stored schema** (e.g., v3). Never let a reader accidentally write back a v3 model through an unguarded save API.

## 8. Java: Reading Raw BSON with `MongoTemplate`

### 8.1. Why Use Raw `Document` in the Lab?

If a Java class only has:

~~~java
@Field("pricing")
private Pricing pricing;
~~~

it does not automatically know how to read legacy **rent_vnd** or **monthly_rent_vnd** without conversion logic. Using **org.bson.Document** at the reader boundary lets you inspect exactly what was stored.

The application can:

1. Query via `MongoTemplate.getCollection` or the MongoDB driver.
2. Receive raw BSON `Document`.
3. Dispatch on `schema_version`.
4. Convert to the canonical read model.
5. Return `ListingView` to services/APIs.

### 8.2. Reader Does Not Mutate the Source

In the following example, the reader is **read-only**. No save/update happens inside the adapter.

~~~java
package com.example.mongo425.read;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Date;

import org.bson.Document;
import org.bson.types.Decimal128;

import com.example.mongo425.domain.ListingView;
import com.example.mongo425.domain.Money;
import com.example.mongo425.domain.PublicationStatus;

public final class VersionedListingReader {

    public ListingView read(Document raw) {
        if (raw == null) {
            throw new IllegalArgumentException(
                "Document must not be null"
            );
        }
        int version = detectVersion(raw);

        return switch (version) {
            case 1 -> readV1(raw);
            case 2 -> readV2(raw);
            case 3 -> readV3(raw);
            default -> throw new UnsupportedSchemaVersionException(
                "Unsupported schema_version=" + version
            );
        };
    }

    private int detectVersion(Document raw) {
        if (!raw.containsKey("schema_version")) {
            // Valid only because a legacy contract exists for this collection.
            return 1;
        }

        Object value = raw.get("schema_version");
        if (!(value instanceof Integer version)) {
            throw new InvalidListingSchemaException(
                "schema_version must be BSON Int32"
            );
        }

        if (version < 1) {
            throw new InvalidListingSchemaException(
                "schema_version must be positive"
            );
        }
        return version;
    }

    private ListingView readV1(Document raw) {
        String id = requiredString(raw, "_id");
        String tenant = requiredString(raw, "tenant_id");
        String title = requiredString(raw, "title");
        String city = requiredString(raw, "city");

        Object rent = raw.get("rent_vnd");
        if (!(rent instanceof Integer)
                && !(rent instanceof Long)) {
            throw new InvalidListingSchemaException(
                "v1 rent_vnd must be Int32 or Int64"
            );
        }
        BigDecimal amount = BigDecimal.valueOf(
            ((Number) rent).longValue()
        );

        Object active = raw.get("active");
        if (!(active instanceof Boolean flag)) {
            throw new InvalidListingSchemaException(
                "v1 active must be Boolean"
            );
        }

        return canonical(
            id, tenant, title,
            new Money(amount, "VND"),
            city,
            flag ? PublicationStatus.PUBLISHED
                 : PublicationStatus.DRAFT,
            requiredInstant(raw, "created_at")
        );
    }

    private ListingView readV2(Document raw) {
        String id = requiredString(raw, "_id");
        String tenant = requiredString(raw, "tenant_id");
        String title = requiredString(raw, "title");

        Document location = requiredDocument(
            raw, "location"
        );

        return canonical(
            id, tenant, title,
            new Money(
                requiredDecimal128(
                    raw, "monthly_rent_vnd"
                ),
                "VND"
            ),
            requiredString(location, "city_code"),
            requiredStatus(raw, "status"),
            requiredInstant(raw, "published_at")
        );
    }

    private ListingView readV3(Document raw) {
        String id = requiredString(raw, "_id");
        String tenant = requiredString(raw, "tenant_id");
        String title = requiredString(raw, "title");

        Document pricing = requiredDocument(
            raw, "pricing"
        );
        Document monthly = requiredDocument(
            pricing, "monthly"
        );
        Document address = requiredDocument(
            raw, "address"
        );
        Document publication = requiredDocument(
            raw, "publication"
        );

        return canonical(
            id, tenant, title,
            new Money(
                requiredDecimal128(monthly, "amount"),
                requiredString(monthly, "currency")
            ),
            requiredString(address, "city_code"),
            requiredStatus(publication, "status"),
            requiredInstant(publication, "published_at")
        );
    }

    private static ListingView canonical(
            String id,
            String tenant,
            String title,
            Money money,
            String city,
            PublicationStatus status,
            Instant publishedAt) {
        if (money.amount().signum() < 0) {
            throw new InvalidListingSchemaException(
                "Negative rent amount"
            );
        }
        if (!"VND".equals(money.currency())) {
            throw new InvalidListingSchemaException(
                "Lab only supports currency VND"
            );
        }
        return new ListingView(
            id, tenant, title, money, city,
            status, publishedAt
        );
    }

    private static String requiredString(
            Document source,
            String key) {
        Object value = source.get(key);
        if (!(value instanceof String result)
                || result.isBlank()) {
            throw new InvalidListingSchemaException(
                "Missing/invalid String field: " + key
            );
        }
        return result;
    }

    private static Document requiredDocument(
            Document source,
            String key) {
        Object value = source.get(key);
        if (!(value instanceof Document nested)) {
            throw new InvalidListingSchemaException(
                "Missing/invalid embedded document: " + key
            );
        }
        return nested;
    }

    private static BigDecimal requiredDecimal128(
            Document source,
            String key) {
        Object value = source.get(key);
        if (!(value instanceof Decimal128 decimal)) {
            throw new InvalidListingSchemaException(
                "Missing/invalid Decimal128 field: " + key
            );
        }
        return decimal.bigDecimalValue();
    }

    private static Instant requiredInstant(
            Document source,
            String key) {
        Object value = source.get(key);
        if (!(value instanceof Date date)) {
            throw new InvalidListingSchemaException(
                "Missing/invalid BSON Date field: " + key
            );
        }
        return date.toInstant();
    }

    private static PublicationStatus requiredStatus(
            Document source,
            String key) {
        String name = requiredString(source, key);
        try {
            return PublicationStatus.valueOf(name);
        } catch (IllegalArgumentException badStatus) {
            throw new InvalidListingSchemaException(
                "Unsupported status: " + name
            );
        }
    }
}
~~~

Dedicated exceptions:

~~~java
package com.example.mongo425.read;

public class InvalidListingSchemaException
        extends RuntimeException {
    public InvalidListingSchemaException(String message) {
        super(message);
    }
}
~~~

~~~java
package com.example.mongo425.read;

public class UnsupportedSchemaVersionException
        extends RuntimeException {
    public UnsupportedSchemaVersionException(String message) {
        super(message);
    }
}
~~~

Each public class must reside in a properly named Java file. The snippet uses **Java 17 pattern matching for `instanceof`** and **switch expressions**.

### 8.3. Why Not Silently Coerce Every Data Type?

Cases like:

~~~javascript
{ rent_vnd: "12500000" }
{ rent_vnd: 12500000.99 }
{ monthly_rent_vnd: NumberDouble(12500000.5) }
~~~

all **look like rent amounts** yet violate the example contract.

If a reader blindly executes:

~~~java
new BigDecimal(raw.get("rent_vnd").toString())
~~~

it turns bad data into falsely valid values, masking writer/import bugs and causing financial discrepancies. Prefer explicit, verified compatibility rules for each allowed type.

### 8.4. Why `BigDecimal.valueOf` for v1?

The v1 contract is Int32/Int64 **in VND**. Converting from `long` to `BigDecimal` is **unit-preserving**.

Never multiply or divide by 1,000,000 unless the legacy schema explicitly defined `rent_vnd` in millions of VND.

### 8.5. `Decimal128` and Non-Finite Values

MongoDB `Decimal128` includes special BSON/IEEE 754 Decimal128 values. Converting NaN/Infinity to Java `BigDecimal` is invalid. Readers should treat them as **invalid prices**, never as valid rent.

The example rejects conversion whenever `Decimal128` cannot yield a finite `BigDecimal`. Production adapters can catch conversion exceptions and translate them into domain-specific errors for metric tracking.

### 8.6. Fields Absent from `ListingView`

A raw document may contain:

~~~javascript
{ legacy_note: "imported-2019" }
~~~

The reader excludes this field from the API. **Omitting `legacy_note` from the read model** does not remove it from MongoDB.

If after reading, the application takes `ListingView` and **saves it over the raw document**, unknown fields disappear. Keep **read-only projections** and **write models** strictly separate.

## 9. Using the Reader with Spring Data MongoDB

### 9.1. Read Adapter with `MongoTemplate`

~~~java
package com.example.mongo425.read;

import com.example.mongo425.domain.ListingView;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ListingReadRepository {

    private final MongoTemplate template;
    private final VersionedListingReader reader;

    public ListingReadRepository(
            MongoTemplate template) {
        this.template = template;
        this.reader = new VersionedListingReader();
    }

    public ListingView findForTenant(
            String id,
            String authenticatedTenantId) {
        Document filter = new Document("_id", id)
            .append("tenant_id", authenticatedTenantId);

        Document raw = template
            .getCollection("rental_listings_425")
            .find(filter)
            .first();

        return raw == null ? null : reader.read(raw);
    }
}
~~~

In this example:

- **MongoTemplate.getCollection()** returns the MongoDB Java driver collection API with raw `Document`.
- The filter uses **stored BSON names** such as `tenant_id`.
- The reader converts to `ListingView`.
- No save/update is performed.

### 9.2. Tenant Authorization Must Happen Before Conversion

Correct:

~~~javascript
{
  _id: requestedId,
  tenant_id: authenticatedTenantId
}
~~~

Missing tenant filter:

~~~javascript
{ _id: requestedId }
~~~

allows the service to fetch another tenant's document and feed it to the reader, risking data leaks or inappropriate logs. **Never trust an unauthenticated client-supplied `tenantId`**.

Read compatibility must never weaken authorization, visibility, or data residency.

### 9.3. When to Use a Spring Custom Converter?

Spring Data provides **custom conversions** to map BSON into specialized Java types. You can register a **@ReadingConverter** to avoid calling adapters manually across repositories.

However, evaluate carefully:

- Where in the mapping lifecycle the converter applies.
- Whether `_class` type metadata is required.
- Conflicts with built-in conversions.
- Which types the converter matches.
- Whether query mapping and write conversion are symmetric.
- Whether someone might accidentally use the converter to **save** a read model.

With three versions following distinct rules, an **explicit boundary reader** is often easier to control. When using custom converters, write thorough integration tests against real MongoDB, especially on legacy documents lacking `_class`.

### 9.4. Read Model and Persistence Entity Need Not Be the Same Class

~~~text
Stored documents (heterogeneous)
        |
VersionedListingReader
        |
ListingView (immutable read DTO)

Write API
        |
Validated ListingWriteCommand
        |
CurrentSchemaWriter (schema v3)
        |
MongoDB
~~~

Separating them prevents business code from saving a normalized object that lacks raw fields.

## 10. Unit Testing Each Adapter

### 10.1. Benefits of Raw BSON Fixtures

Unit tests do not need a real MongoDB instance to verify **pure Java `Document` → `ListingView` conversion**. They are true unit tests because the adapter performs no I/O.

Example using JUnit Jupiter:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Date;

import org.bson.Document;
import org.junit.jupiter.api.Test;

class VersionedListingReaderTest {

    private final VersionedListingReader reader =
        new VersionedListingReader();

    @Test
    void legacyV1WithoutMarkerConvertsToCanonical() {
        Document raw = new Document("_id", "b425-v1")
            .append("tenant_id", "tenant-001")
            .append("title", "Studio")
            .append("rent_vnd", 12500000L)
            .append("city", "HCM")
            .append("active", true)
            .append(
                "created_at",
                Date.from(Instant.parse(
                    "2026-01-15T09:00:00Z"
                ))
            );

        ListingView view = reader.read(raw);

        assertEquals("b425-v1", view.id());
        assertEquals("HCM", view.cityCode());
        assertEquals(
            new BigDecimal("12500000"),
            view.monthlyRent().amount()
        );
        assertEquals("VND", view.monthlyRent().currency());
        assertEquals(
            PublicationStatus.PUBLISHED,
            view.status()
        );
    }

    @Test
    void unknownVersionIsNotSilentlyDowngraded() {
        Document future = new Document("_id", "b425-v4")
            .append("schema_version", 4);

        assertThrows(
            UnsupportedSchemaVersionException.class,
            () -> reader.read(future)
        );
    }

    @Test
    void nullMarkerIsNotLegacyV1() {
        Document invalid = new Document("_id", "b425-null")
            .append("schema_version", null);

        assertThrows(
            InvalidListingSchemaException.class,
            () -> reader.read(invalid)
        );
    }
}
~~~

Add imports for your domain/read packages per your project structure. This snippet highlights the key assertions.

### 10.2. Testing v2/v3

Unit fixtures should cover:

- v2 with **Decimal128**, `location.city_code`, `status`, `published_at`.
- v3 with `pricing.monthly.amount`/`currency`, `address`, and `publication`.
- Equivalent money/city/status values across versions yielding **identical `ListingView`s**.
- Unsupported v3 currencies being rejected rather than converted automatically.

### 10.3. Testing Malformed BSON

| Case | Expected |
| --- | --- |
| Missing `schema_version` and missing `rent_vnd` | Invalid schema |
| `schema_version: null` | Invalid schema |
| `schema_version: "3"` | Invalid schema |
| `schema_version: 99` | Unsupported schema |
| `rent_vnd` is String | Invalid schema |
| `monthly_rent_vnd` is Double | Invalid schema |
| `pricing.monthly.amount` missing | Invalid schema |
| `publication.status = "BLOCKED"` | Invalid/unsupported status |
| `_id` not String per contract | Invalid schema |
| Blank `tenant_id` | Invalid schema |
| Negative rent | Invalid schema |
| `published_at` not Date | Invalid schema |

Never test only three happy-path fixtures and assume the adapter handles all legacy data.

### 10.4. Property-Based Tests

If the project uses property-based testing, verify:

> For every valid v1 integer rent within the allowed rental range and `currency=VND`, converting v1 to canonical preserves exact arithmetic value.

Ensure the generator respects domain bounds; never silently accept negative prices, overflow, or invalid types.

## 11. Integration Testing with Real MongoDB

### 11.1. Why Unit Tests Are Not Enough

Java unit tests build `new Document(...)`, whereas MongoDB Server stores and returns:

- BSON Int32 or Int64 depending on operation.
- BSON Decimal128.
- BSON Date with millisecond precision.
- Nested Documents and Arrays.
- Missing/null fields.

Integration tests must verify **actual BSON types** round-tripped through the driver and server.

### 11.2. Using an Isolated Test Collection

With Spring Boot and Testcontainers MongoDB (appropriate versions):

~~~java
@DataMongoTest
@Testcontainers
class VersionedListingRepositoryIntegrationTest {

    @Container
    static MongoDBContainer mongo =
        new MongoDBContainer(
            DockerImageName.parse("mongo:7.0")
        );

    @DynamicPropertySource
    static void configure(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.mongodb.uri",
            mongo::getReplicaSetUrl
        );
    }

    @Autowired MongoTemplate template;

    // Seed raw v1/v2/v3 in an isolated container.
    // Read via ListingReadRepository, assert ListingView.
}
~~~

Imports and Testcontainers module coordinates must match your Testcontainers/Spring Boot versions. This is a **test skeleton**, not a standalone compilable file.

### 11.3. Key Assertions

- Reader accepts legacy v1 documents without a marker.
- Reader accepts explicit v2/v3 from the real database.
- `Decimal128` is returned by the driver with the right type.
- `Date` converts to `Instant` with matching timestamp.
- `tenant_id` filter prevents cross-tenant lookups.
- Inserting a `schema_version=4` document fails cleanly without causing writes.
- Read documents **remain unmodified** afterward; re-read raw BSON to confirm.

### 11.4. Never Reset Fixtures Against Production

A test calling **deleteMany({})** can wipe an entire collection if the URI is misconfigured. Only run this when **verified to target an isolated MongoDB Testcontainer**. Add fail-fast guards checking database name, URI, credentials, and network policy.

## 12. Multi-Version Queries: Readable Does Not Mean Queryable

### 12.1. The Biggest Adapter Trap

Reading by `_id`:

~~~text
findById -> raw v1 -> adapter -> ListingView
~~~

may work flawlessly. Yet a search API filtering by city:

~~~javascript
db.rental_listings_425.find({
  "address.city_code": "HCM"
});
~~~

returns only v3; it **misses v1 and v2** because field names differ.

Thus **read compatibility has two independent parts**:

1. **Query compatibility**: does MongoDB match the right documents?
2. **Materialization compatibility**: once found, does the adapter convert them properly?

### 12.2. Version-Scoped `$or`

In `mongosh`:

~~~javascript
db.rental_listings_425.find({
  tenant_id: "tenant-001",
  $or: [
    {
      schema_version: { $exists: false },
      city: "HCM"
    },
    {
      schema_version: 2,
      "location.city_code": "HCM"
    },
    {
      schema_version: 3,
      "address.city_code": "HCM"
    }
  ]
});
~~~

The query checks only paths defined in the contract. Including `schema_version` prevents a v3 document carrying a stale legacy `city` field from accidentally matching the v1 branch.

### 12.3. Enforce Tenant Filtering Properly

In multi-tenant applications, attaching `tenant_id` from the **authenticated identity** at the root query is mandatory. Never run:

~~~javascript
db.rental_listings_425.find({
  $or: [ /* cities */ ]
});
~~~

and filter tenants in Java after loading documents from other tenants. That increases data exposure risk and I/O cost.

### 12.4. Is Filtering After Conversion Acceptable?

The idea:

~~~text
Load 1,000,000 docs
  -> convert all
  -> filter cityCode="HCM" in Java
~~~

is generally unworkable because:

- Massive data scanning and network transfer.
- Broken pagination, sorting, and count semantics.
- High app CPU and memory usage.
- Security hazards if tenant filtering is not enforced at the database.

It might serve only for tiny/lab datasets; production requires a proper query strategy and indexes.

### 12.5. Sorting Across Multiple Date Fields

v1 uses **created_at**, v2 uses **published_at**, v3 uses **publication.published_at**. A query sorting by:

~~~javascript
.sort({ "publication.published_at": -1 })
~~~

finds v1/v2 lacking that field; global order no longer reflects publication time as requested.

To achieve a **canonical sort** across mixed versions:

- Normalize the field in aggregation and sort afterward; or
- Backfill a shared **stable sort key** field; or
- Query per version and merge-sort in the application with strict pagination controls; or
- Migrate before enabling sort-dependent features.

Offset pagination over multi-version datasets with inconsistent sort keys easily produces duplicates or skipped rows.

## 13. Index Strategy During Three Coexisting Schemas

### 13.1. Different Field Paths Need an Index Plan

For example, city queries:

~~~javascript
{
  tenant_id: "tenant-001",
  city: "HCM"
}
~~~

and:

~~~javascript
{
  tenant_id: "tenant-001",
  "location.city_code": "HCM"
}
~~~

and:

~~~javascript
{
  tenant_id: "tenant-001",
  "address.city_code": "HCM"
}
~~~

may require **different compound indexes** during transition.

### 13.2. Lab Index Examples

~~~javascript
const listings = db
  .getSiblingDB("mongo_evolution_lab_425")
  .getCollection("rental_listings_425");

listings.createIndex(
  { tenant_id: 1, city: 1 },
  { name: "ix425_v1_tenant_city" }
);

listings.createIndex(
  {
    tenant_id: 1,
    schema_version: 1,
    "location.city_code": 1
  },
  { name: "ix425_v2_tenant_city" }
);

listings.createIndex(
  {
    tenant_id: 1,
    schema_version: 1,
    "address.city_code": 1
  },
  { name: "ix425_v3_tenant_city" }
);
~~~

These are **lab** index examples. Never blindly create all three in production simply because three schemas exist: evaluate query patterns, selectivity, write overhead, storage, and actual query plans.

### 13.3. Does `$or` Guarantee Index Usage?

No. The optimizer picks plans based on statistics, document counts, and predicates. With `$or`, having an index per branch usually improves execution potential, yet **does not guarantee** the query uses every index as hoped.

Inspect:

~~~javascript
listings.find({
  tenant_id: "tenant-001",
  $or: [
    {
      schema_version: { $exists: false },
      city: "HCM"
    },
    {
      schema_version: 2,
      "location.city_code": "HCM"
    },
    {
      schema_version: 3,
      "address.city_code": "HCM"
    }
  ]
}).explain("executionStats");
~~~

Examine **winningPlan**, **totalKeysExamined**, **totalDocsExamined**, **nReturned**, and latency in a representative environment.

### 13.4. Price Comparisons Must Share the Same Unit

v1 is Int64 VND, v2 is Decimal128 VND, and v3 is Decimal128 VND. MongoDB compares numeric BSON types consistently, yet normalization must enforce:

- Never allow missing currency in v3.
- Never assume non-VND currencies have the same value.
- Never convert currencies at current spot rates if the contract requires historical amounts.

If v1 stored rent in **millions of VND** instead of VND, range queries spanning v1 and v3 would no longer compare identical quantities.

### 13.5. Avoid Keeping Legacy Indexes Forever

Once v1/v2 documents and old writers are gone:

1. Verify version distribution.
2. Verify queries no longer touch legacy fields.
3. Compare index usage and performance.
4. Drop old indexes via your change procedure.

Every index adds storage and write-maintenance cost, so read compatibility carries real operational expense.

## 14. Transforming Inside an Aggregation Pipeline

### 14.1. When to Use Aggregation?

If you need to:

- Search by canonical city.
- Sort by canonical `publishedAt`.
- Compute aggregate statistics across versions.
- Return slim projections without materializing full raw documents in the app.

aggregation can help. The example below is a **read-only pipeline**; it has no `$merge` or `$out`.

### 14.2. Normalizing Schema Version

For v1 missing a marker, distinguish missing from explicit null:

~~~javascript
{
  $set: {
    normalized_version: {
      $cond: [
        {
          $eq: [
            { $type: "$schema_version" },
            "missing"
          ]
        },
        1,
        "$schema_version"
      ]
    }
  }
}
~~~

Never blindly use **$ifNull** if explicit `schema_version: null` must be flagged as malformed rather than legacy.

### 14.3. Pipeline Normalizing City, Rent, and Date

In `mongosh`, targeting the lab database:

~~~javascript
const lab = db.getSiblingDB("mongo_evolution_lab_425");
const listings = lab.getCollection("rental_listings_425");

const pipeline = [
  {
    $match: {
      labTag: "evolution425-v1",
      tenant_id: "tenant-001"
    }
  },
  {
    $set: {
      normalized_version: {
        $cond: [
          {
            $eq: [
              { $type: "$schema_version" },
              "missing"
            ]
          },
          1,
          "$schema_version"
        ]
      }
    }
  },
  {
    $set: {
      canonical_city: {
        $switch: {
          branches: [
            {
              case: {
                $eq: ["$normalized_version", 1]
              },
              then: "$city"
            },
            {
              case: {
                $eq: ["$normalized_version", 2]
              },
              then: "$location.city_code"
            },
            {
              case: {
                $eq: ["$normalized_version", 3]
              },
              then: "$address.city_code"
            }
          ],
          default: null
        }
      },
      canonical_rent_vnd: {
        $switch: {
          branches: [
            {
              case: {
                $eq: ["$normalized_version", 1]
              },
              then: { $toDecimal: "$rent_vnd" }
            },
            {
              case: {
                $eq: ["$normalized_version", 2]
              },
              then: "$monthly_rent_vnd"
            },
            {
              case: {
                $eq: ["$normalized_version", 3]
              },
              then: "$pricing.monthly.amount"
            }
          ],
          default: null
        }
      },
      canonical_published_at: {
        $switch: {
          branches: [
            {
              case: {
                $eq: ["$normalized_version", 1]
              },
              then: "$created_at"
            },
            {
              case: {
                $eq: ["$normalized_version", 2]
              },
              then: "$published_at"
            },
            {
              case: {
                $eq: ["$normalized_version", 3]
              },
              then: "$publication.published_at"
            }
          ],
          default: null
        }
      }
    }
  },
  {
    $match: {
      normalized_version: { $in: [1, 2, 3] },
      canonical_city: "HCM"
    }
  },
  {
    $project: {
      _id: 1,
      tenant_id: 1,
      title: 1,
      normalized_version: 1,
      canonical_city: 1,
      canonical_rent_vnd: 1,
      canonical_published_at: 1
    }
  },
  {
    $sort: {
      canonical_published_at: -1,
      _id: 1
    }
  }
];

printjson(listings.aggregate(pipeline).toArray());
~~~

**Safety/semantics note:** This pipeline demonstrates normalization on **contract-validated** data and is not a complete replacement for Java reader validation:

- Unknown versions are filtered out by `$match`; **never use this result to conclude all documents were readable**.
- If v1 `rent_vnd` holds a bad string, **$toDecimal** may coerce it per MongoDB rules or throw; pre-validate inputs to avoid silently legitimizing corrupt data.
- If fields are missing, canonical fields become null/missing.
- The pipeline does not verify VND currency for v3.
- Expression-based normalization can make index utilization for filters/sorts harder.

In production, separate **invalid/unknown detection** from reporting pipelines so corrupt data is never hidden.

### 14.4. Post-Normalization Sorting Has Trade-Offs

Sorting by a pipeline-computed **canonical_published_at** generally cannot directly leverage indexes on the source fields. On large datasets this can:

- Increase CPU/memory usage.
- Increase execution latency.
- Trigger disk spill/memory limits depending on deployment.

If the API paginates millions of documents, **backfilling a canonical sort field** may be far better than computing it on every read.

### 14.5. Aggregation Does Not Perform Magic Migration

Running:

~~~javascript
listings.aggregate(pipeline);
~~~

does not mutate stored documents unless the pipeline includes side-effect stages like **$merge** or **$out** (with matching privileges and conditions). `canonical_city` and `canonical_rent_vnd` exist only in the **returned output**.

## 15. Correctness in Data Transformation

### 15.1. Lossless vs. Lossy

A conversion that is **lossless under the contract** preserves enough information to convey the exact same business meaning.

Example:

~~~text
rent_vnd Int64 12500000
  -> Decimal128/BigDecimal 12500000.00
~~~

preserves the exact VND numeric value.

A conversion can be **lossy**:

~~~text
status = "BANNED"
  -> active = false
~~~

because you cannot recover whether `false` meant BANNED, ARCHIVED, or DRAFT.

### 15.2. Invariants to Preserve

- Rent neither changes units nor value.
- Never drop `tenantId`.
- Never turn a suspended/locked status into published.
- Never shift timestamps into the wrong timezone.
- `_id` preserves identity.
- Expose only fields the actor is authorized to view.
- Never invent unsubstantiated PII/defaults.

### 15.3. Dangerous Default Values

Wrong:

~~~java
BigDecimal rent = missing
    ? BigDecimal.ZERO
    : parsedRent;
~~~

If rent is missing, defaulting to 0 can surface the listing in “cheapest” search results, breaking business logic.

Depending on the contract, instead:

- Reject as invalid data.
- Return `null` under an explicit API contract.
- Hide the listing from search and send it to a repair queue.
- Apply a known historical default only when formally approved.

### 15.4. Null and Missing

Three states to evaluate:

~~~javascript
{ /* field absent */ }
{ field: null }
{ field: "" }
~~~

These three do not always share the same meaning. During migration, a missing field may mean “legacy schema,” explicit null may mean “user left unset,” and an empty string may be an input bug.

### 15.5. UTC and `Date`

MongoDB BSON Date stores an instant timestamp; the Java driver typically materializes it as **java.util.Date**, converted via **toInstant()**.

Never turn an instant like:

~~~text
2026-01-15T09:00:00Z
~~~

into a `LocalDateTime` and attach an arbitrary timezone. If the business needs a location's timezone (e.g., appointment schedules in Vietnam), store `ZoneId` explicitly per contract.

### 15.6. Currency Must Be Explicit When Expanding Markets

In this example, v1/v2 assume VND because the legacy contract fixed it. If USD/SGD listings appear later, never convert v3 prices into VND at “current” exchange rates inside a reader without explicit rate timestamps and historical sources.

Currency schema evolution likely needs a **new version** and dedicated policy.

## 16. Mixed-Schema Read Strategies with Spring Data Repository

### 16.1. Is One `@Document` Class for v3 Enough?

~~~java
@Document("rental_listings_425")
public class ListingEntity {
    @Field("pricing")
    private Pricing pricing;
}
~~~

This class describes **v3** and will not map v1/v2 `rent_vnd` or `monthly_rent_vnd` into `pricing`.

If Spring Data `findById` loads a v1 document into a v3 entity without a custom converter, `pricing` becomes `null` and business logic fails.

### 16.2. Two Options

**Option A — Dedicated Read Adapter:**

~~~text
MongoTemplate raw Document
 -> VersionedListingReader
 -> ListingView
~~~

**Option B — Custom Mapping Converters:**

~~~text
MongoRepository / MongoTemplate
 -> MappingMongoConverter + ReadingConverter
 -> ListingView / matching entity
~~~

Option B integrates more deeply, yet requires testing:

- Query generation per version.
- Type metadata.
- Write conversions.
- Interactions with nested properties.
- Read-only projection edge cases.

### 16.3. Do Not Overload One Entity with All Three Roles

If `ListingEntity` simultaneously declares:

~~~java
Long rentVnd;
BigDecimal monthlyRentVnd;
Pricing pricing;
~~~

services might use the wrong field or save a v1 record with half-populated v3 fields. A **read adapter** returning a canonical DTO is easier to govern.

### 16.4. CQRS / Read Models as an Architectural Option

When multi-version querying grows too complex, you can maintain a **separate read collection/index** holding only canonical fields, kept updated via migrations or Change Stream consumers. This carries sync overhead and eventual consistency—it is not “free.”

You do not need CQRS for every collection; consider it when queries are complex, volume is high, or many consumers need a canonical view.

## 17. Read Then Write Back: What Is Lazy Read-Repair?

### 17.1. Read-Only Transformation

~~~text
Read raw v1
    |
Convert to canonical
    |
Return response

Stored document stays v1
~~~

### 17.2. Read-Repair

~~~text
Read raw v1
    |
Convert to canonical
    |
Return response
    |
Optional background/synchronous repair
    |
Write stored document v3
~~~

Read-repair is also called **lazy migration on read** when reading a document triggers upgrading its stored schema.

Pros:

- Frequently read documents gradually migrate to the new schema.
- Avoids backfilling everything before deployment.
- Spreads migration work proportionally to traffic.

Cons:

- Reads unexpectedly generate writes.
- “Cold” documents may never migrate.
- Contention with concurrent writers updating the same document.
- Increases write latency, index maintenance, and oplog/Change Streams traffic.
- Grants write permissions to otherwise read-only processes.
- A repair failure can break user-facing reads if placed in the synchronous path carelessly.

### 17.3. Never Save `ListingView` to Migrate

Wrong:

~~~java
ListingView view = reader.read(raw);
repository.save(view);  // risk of wrong collection/shape/metadata
~~~

`ListingView` lacks legacy fields, is not a write entity, and is unsafe for full-document replacement. It can strip metadata, tags, and fields outside the read model.

### 17.4. Repair Needs an Explicit Migration Policy

A valid repair must:

1. Know the exact source schema.
2. Have complete source data to build the target schema without guessing.
3. Enforce optimistic concurrency or a revision guard.
4. Preserve fields outside migration scope.
5. Implement idempotency and retry policies.
6. Emit success/conflict/error metrics.
7. Have a backup/rollback plan.
8. Ensure old writers will not write the old schema back, or handle conflicts explicitly.

### 17.5. Compare-and-Set (CAS)

Suppose documents carry a `revision` updated by every writer. Read-repair observes `revision=7`, then writes:

~~~javascript
db.rental_listings_425.updateOne(
  {
    _id: "b425-cas-example",
    tenant_id: "tenant-001",
    schema_version: 2,
    revision: NumberLong("7")
  },
  {
    $set: {
      schema_version: 3,
      pricing: {
        monthly: {
          amount: NumberDecimal("12500000.00"),
          currency: "VND"
        }
      }
    },
    $inc: {
      revision: NumberLong("1")
    }
  }
);
~~~

If another writer already bumped `revision` to 8, **matchedCount=0**: the repair aborts without overwriting and can re-read. Note:

- This snippet is **not a complete migration** because it only sets `pricing`/`schema_version` without moving location/status/dates or unsetting legacy fields.
- Never run against live data without complete mapping and validation.
- CAS is only trustworthy if **every writer honors the revision contract**. If an old service updates without incrementing `revision`, the guard misses the concurrent write.
- A schema upgrade may require an atomic single-document update or multi-document transaction depending on scope.

### 17.6. Do Not Treat `schema_version` as a CAS Token

If the filter is only:

~~~javascript
{ _id: id, schema_version: 2 }
~~~

two writers can still modify `rentAmount` while `schema_version` remains 2. A reader repairing using a previously read rent can write back the **stale price** even though `schema_version` matched.

Preventing lost updates requires **revision**, full source-field predicates, or an atomic server-side transformation. Filtering solely on `schema_version` does not prevent all races.

### 17.7. Asynchronous or Synchronous Repair?

**Synchronous:**

- Response waits for the repair write.
- Repair failures add latency or break reads.
- Guarantees read-after-repair, yet impacts users.

**Asynchronous:**

- Read response does not wait on migration.
- Needs queues, idempotency, retries, and dead-letter handling.
- Documents stay in the old schema temporarily.
- Must handle ordering and concurrent updates.

In most cases, start with a **read-only adapter** and run migrations in a **separate job** when possible to contain blast radius.

## 18. Why Is Backfill Still Needed Even with Read-Repair?

Read-repair only runs when a document is read. Rarely accessed documents:

~~~text
Hot 20% documents:
  read daily -> likely repaired

Cold 80% documents:
  rarely read -> may stay v1 for months
~~~

If the goal is retiring v1 support or dropping legacy indexes, you still need an **offline/backfill migration** and completion verification.

### 18.1. Batched Backfill with Checkpoints

A migration job should:

- Iterate via stable keyset pagination or targeted queries.
- Select only documents matching versions slated for migration.
- Read/validate/transform using verified adapters.
- Write with CAS/idempotency.
- Limit batch size, CPU/IOPS, and concurrency.
- Persist checkpoints and progress metrics.
- Route malformed records to dead-letter/quarantine.
- Track remaining document counts per version.

Avoid:

~~~text
Load 20M docs into RAM
 -> rewrite entire collection unthrottled
~~~

on a production cluster without planning.

### 18.2. Safe Re-Runs

An idempotent migration can restart after a crash without:

- Multiplying rent repeatedly.
- Duplicating nested structures.
- Downgrading versions.
- Erasing new fields written by other writers.

Re-running a migration on an already-upgraded v3 document should be a **no-op** rather than altering valid data.

### 18.3. Reconciliation

After backfill:

- Count v1/v2/v3 documents.
- Compare before/after ID sets.
- Compare business totals (such as total rent where applicable).
- Check for missing/null/invalid fields.
- Verify canonical output on sampled records.
- Watch for newly written old-version documents.

Counting `version=3` alone does not prove all v3 documents are valid.

## 19. Expand–Migrate–Contract in Multi-Version Rollouts

### 19.1. Phase A — Expand Readers

Deploy readers that understand **v1/v2/v3** while **writers remain unchanged**:

~~~text
App release R1:
  Read: v1 + v2 + v3
  Write: v2 (keep existing older schema)
~~~

During a rolling deployment, old apps still read v2 because no v3 writer is active yet. Verify forward and backward compatibility for both old and new readers.

### 19.2. Phase B — New Writer

After all old readers are gone or proven able to handle v3:

~~~text
App release R2:
  Read: v1 + v2 + v3
  Write: v3
~~~

Never flip the v3 writer on as soon as one new instance deploys if older running instances cannot read v3.

### 19.3. Phase C — Migrate Backlog

Backfill v1/v2 → v3:

~~~text
Collection:
  v1 count decreases
  v2 count decreases
  v3 count increases
~~~

Run throttled jobs with reconciliation. Throughout this phase, readers continue supporting legacy schemas.

### 19.4. Phase D — Contract

Only drop v1/v2 adapters and legacy indexes when:

- No old writers remain.
- No legacy data remains (or a cold-data read policy covers it).
- Backup/restore compatibility has been verified.
- Legacy mobile/offline clients no longer submit old schemas.
- Queries/metrics no longer depend on old fields.
- A rollback policy is defined.

### 19.5. Timeline

~~~text
Time --------------------------------------------------->

Deploy compatible reader
      |
      +----- All instances can read v1/v2/v3
                      |
                      +--- Switch writer to v3
                                 |
                                 +--- Backfill v1/v2
                                            |
                                            +--- Verify
                                                     |
                                                     +--- Remove adapters/indexes
~~~

The gate to switch writers is not “code merged,” but **every read path that can touch a v3 document is compatible**.

## 20. Compatibility Matrix: Readers and Writers

| Reader / Writer | Writer v1 | Writer v2 | Writer v3 |
| --- | --- | --- | --- |
| **Reader R1 (v1 only)** | Yes | Not guaranteed | No |
| **Reader R2 (v1+v2)** | Yes | Yes | No |
| **Reader R3 (v1+v2+v3)** | Yes | Yes | Yes |

This matrix assumes the contracts and field types from this lesson; “Yes” means mapping can decode the document, **not that all business logic, indexes, and API behaviors are automatically valid**.

### 20.1. Forward Compatibility Has Limits

Reader v2 cannot reliably understand v3 if field semantics change. Mitigation strategies include:

- Temporarily dual-writing old and new fields.
- Deploying expanded readers first.
- Keeping writer v2 during the overlap window.
- Gating writer v3 behind a feature flag.

### 20.2. Dual-Write Risks

~~~javascript
{
  monthly_rent_vnd: NumberDecimal("12500000"),
  pricing: {
    monthly: {
      amount: NumberDecimal("12500000"),
      currency: "VND"
    }
  }
}
~~~

If the two fields diverge:

- Which field is the source of truth?
- Which writer updated last?
- Which field does the reader prefer?
- Is there a cleanup migration?

Dual-write can bridge short-term compatibility, yet introduces a **dual-source-of-truth** hazard; define clear precedence rules, metrics, and an end date.

### 20.3. Mixed Reads vs. Mixed Writes

Supporting multiple versions on **read** differs from letting APIs **write** multiple versions:

~~~text
Read support: v1, v2, v3
Write target: v3 only
~~~

is simpler and avoids generating new legacy shapes. If old writers must still operate, define policies and conversions when updating legacy docs without dropping unknown fields.

## 21. Read-Repair and Concurrent Data Modification

### 21.1. Race Condition

~~~text
T0  Reader loads v1: rent=12.5M
T1  User updates rent=13M via Writer
T2  Reader repairs using T0 snapshot
T3  Rent may revert to 12.5M if unguarded
~~~

CAS exists to prevent overwriting fresh updates using a stale read snapshot.

### 21.2. Safeguards

1. **Optimistic locking**: `revision` incremented by all writers.
2. **Conditional updates**: filter on relevant source fields or `revision`.
3. **Atomic update expressions**: server computes from current document values where supported.
4. **Targeted writes**: set only new fields rather than replacing the whole document.
5. **Bounded retries**: on `matchedCount=0`, reload rather than forcing overwrite.
6. **Migration queues**: decouple repair from user-facing reads.

### 21.3. CAS Cannot Fix Stale Sources Under Divergent Contracts

If an old writer does not increment `revision`, an optimistic-lock guard creates an illusion of safety. Audit **all writers** before rollout: REST APIs, batch imports, CDC consumers, admin scripts, and mobile sync.

### 21.4. Are Transactions Always Needed?

When modifying multiple fields within **one document**, MongoDB provides single-document update atomicity. You do not need multi-document transactions simply to set multiple fields on the same document.

When a migration spans **multiple collections/documents** sharing a commit invariant, transactions or sagas/reconciliation may be required by business semantics.

### 21.5. Read-Repair Emits Change Stream Events

Updating a document's schema can emit a **Change Stream event** if enabled. Downstream consumers might:

- Mistake it for a business update.
- Re-index or fire redundant notifications.
- Re-trigger repair loops.

Distinguish **migration metadata updates** from business events via fields, origin headers, producer policies, or consumer logic to prevent feedback loops.

## 22. When Is Server-Side Schema Validation Needed?

### 22.1. Validation Does Not Make Old Documents Disappear

MongoDB supports **$jsonSchema** validation with `validationAction`/`validationLevel` modes. Tightening rules to accept only the new schema still leaves legacy documents **in the collection**.

Never do:

~~~text
1. Switch validator to v3-only
2. Old app still writes v2
3. Ignore outcomes
~~~

as old writers will start hitting validation failures.

### 22.2. Multi-Version Validators

During transition, you can craft rules accepting valid v1/v2/v3 shapes or align validation with rollout policies. Still, multi-version JSON Schemas can get complex; verify performance, null/missing cases, and `validationLevel` behavior.

### 22.3. Enforce v3 After Contract

Once all data and writers are v3, server validation helps block v1/v2 regressions. Test migrations, restores, background jobs, and operational scripts beforehand.

### 22.4. Applications Still Need Validation

Server validators check structure and BSON types, not business rules such as:

- Price matching the right currency.
- Verified tenant authorization.
- Valid publication workflow transitions.
- Users editing only their own listings.

## 23. Caching with Multiple Schemas

### 23.1. Cache Raw or Cache Canonical?

**Cache raw BSON:**

- Preserves original payload for adapters.
- Every cache consumer must still understand multiple versions.

**Cache canonical read model:**

- Fast API reads without repeated conversion.
- Needs versioned cache keys and proper invalidation.
- When adapter logic changes, stale cached normalizations can become wrong.

### 23.2. Cache Keys Should Encode the Contract

Example:

~~~text
listing-view:v3:tenant-001:b425-v1
~~~

Here `v3` in the cache key is the **read-view contract version**, not necessarily the stored `schema_version` of the source document. Keep those two versions distinct.

### 23.3. Cache Invalidation

When a document updates or undergoes read-repair:

- Invalidate the cached `ListingView`.
- Or update cache from ordered, idempotent change events.
- Never continue serving a cached v1 normalization after the underlying rent changed.

If using Change Streams for invalidation, consumers must handle resumes, duplicates, and races properly.

## 24. Monitoring: Knowing How Many Legacy Documents Remain

### 24.1. Minimum Metrics

Track:

- **read_by_schema_version**: read counts across v1/v2/v3.
- **stored_docs_by_schema_version**: stored distribution (periodic counts).
- **unsupported_schema_version_count**.
- **invalid_schema_count** broken down by reason.
- **adapter_latency_ms** per version.
- **read_repair_attempts/success/conflicts/failures** if repairing.
- **backfill_progress**, remaining docs, and ETA.
- **old_writer_detected**: old-schema writes observed after writer cutover.
- Application p50/p95/p99 and read error rates.

### 24.2. Avoid High-Cardinality Metric Labels

Never attach raw **_id** or **tenantId** as metric time-series labels when millions of values exist. Keep labels bounded (version, adapter outcome, deployment) and log/trace IDs safely when investigating.

### 24.3. Counting Documents by Version

An aggregation grouping versions while separating missing from null:

~~~javascript
db.rental_listings_425.aggregate([
  {
    $project: {
      versionKind: {
        $switch: {
          branches: [
            {
              case: {
                $eq: [
                  { $type: "$schema_version" },
                  "missing"
                ]
              },
              then: "v1_missing_marker"
            },
            {
              case: {
                $eq: ["$schema_version", 2]
              },
              then: "v2"
            },
            {
              case: {
                $eq: ["$schema_version", 3]
              },
              then: "v3"
            }
          ],
          default: "unknown_or_invalid"
        }
      }
    }
  },
  {
    $group: {
      _id: "$versionKind",
      docs: { $sum: 1 }
    }
  }
]);
~~~

On large collections, this aggregation performs a full scan; run it via scheduled monitoring/batch jobs rather than per HTTP request.

### 24.4. Reports Must Include Invalid Data

Reporting only:

~~~text
v3 = 98.5%
~~~

without showing **v1/v2/unknown/null** can mislead teams into retiring adapters prematurely. Proper reports show total denominators and unclassified records.

## 25. `mongosh` Lab: Seeding Three Coexisting Schemas

### 25.1. Lab Conventions

Database:

~~~text
mongo_evolution_lab_425
  rental_listings_425
~~~

Uses three documents:

~~~text
b425-v1 -> legacy schema, missing marker
b425-v2 -> schema_version 2
b425-v3 -> schema_version 3
~~~

Do not drop the database/collection, and never touch documents lacking `labTag`.

### 25.2. Idempotent Seed Script

~~~javascript
(() => {
  const lab = db.getSiblingDB(
    "mongo_evolution_lab_425"
  );
  const listings = lab.getCollection(
    "rental_listings_425"
  );
  const tag = "evolution425-v1";

  const docs = [
    {
      _id: "b425-v1",
      labTag: tag,
      tenant_id: "tenant-001",
      title: "Studio near the park",
      rent_vnd: NumberLong("12500000"),
      city: "HCM",
      active: true,
      created_at: ISODate("2026-01-15T09:00:00Z")
    },
    {
      _id: "b425-v2",
      labTag: tag,
      schema_version: 2,
      tenant_id: "tenant-001",
      title: "Apartment with balcony",
      monthly_rent_vnd: NumberDecimal("15000000.00"),
      location: { city_code: "HCM" },
      status: "PUBLISHED",
      published_at: ISODate("2026-01-16T09:00:00Z")
    },
    {
      _id: "b425-v3",
      labTag: tag,
      schema_version: 3,
      tenant_id: "tenant-001",
      title: "Three-bedroom townhouse",
      pricing: {
        monthly: {
          amount: NumberDecimal("23000000.00"),
          currency: "VND"
        }
      },
      address: { city_code: "HN" },
      publication: {
        status: "PUBLISHED",
        published_at: ISODate("2026-01-17T09:00:00Z")
      }
    }
  ];

  for (const doc of docs) {
    listings.replaceOne(
      { _id: doc._id, labTag: tag },
      doc,
      { upsert: true }
    );
  }

  printjson({
    count: listings.countDocuments({ labTag: tag }),
    ids: listings.find(
      { labTag: tag },
      { _id: 1, schema_version: 1 }
    ).sort({ _id: 1 }).toArray()
  });
})();
~~~

Expected result is **count = 3** in a fresh lab collection. In an existing collection, `count` may be higher if you intentionally added other fixtures with the same `labTag`.

**Note:** The `replaceOne` filter requires both **_id and labTag**; if `_id` collides with an unrelated document, upsert fails with duplicate-key instead of overwriting foreign data. Never drop the collection to “fix” that error.

### 25.3. Inspecting Versions with `$type`

~~~javascript
const lab = db.getSiblingDB(
  "mongo_evolution_lab_425"
);
const listings = lab.getCollection(
  "rental_listings_425"
);

printjson(
  listings.aggregate([
    { $match: { labTag: "evolution425-v1" } },
    {
      $project: {
        versionType: { $type: "$schema_version" },
        rentV1Type: { $type: "$rent_vnd" },
        rentV2Type: {
          $type: "$monthly_rent_vnd"
        },
        rentV3Type: {
          $type: "$pricing.monthly.amount"
        },
        cityV1Type: { $type: "$city" },
        cityV2Type: {
          $type: "$location.city_code"
        },
        cityV3Type: {
          $type: "$address.city_code"
        }
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray()
);
~~~

For v1: `versionType` = **missing**, `rentV1Type` = **long**.

For v2: `versionType` = **int**, `rentV2Type` = **decimal**.

For v3: `versionType` = **int**, `rentV3Type` = **decimal**.

### 25.4. Querying Only v3 Misses Results

~~~javascript
printjson(
  listings.find({
    labTag: "evolution425-v1",
    "address.city_code": "HCM"
  }).toArray()
);
~~~

Misses v1/v2 because they do not store city at `address.city_code`; the lab's v3 doc is in HN, so output can be **[]**.

### 25.5. Query Covering v1/v2/v3 Properly

~~~javascript
printjson(
  listings.find({
    labTag: "evolution425-v1",
    tenant_id: "tenant-001",
    $or: [
      {
        schema_version: { $exists: false },
        city: "HCM"
      },
      {
        schema_version: 2,
        "location.city_code": "HCM"
      },
      {
        schema_version: 3,
        "address.city_code": "HCM"
      }
    ]
  }, {
    _id: 1,
    schema_version: 1,
    title: 1
  }).sort({ _id: 1 }).toArray()
);
~~~

Expected results include **b425-v1** and **b425-v2**, excluding **b425-v3** because v3 is in HN.

### 25.6. Version Breakdown

~~~javascript
printjson(
  listings.aggregate([
    { $match: { labTag: "evolution425-v1" } },
    {
      $project: {
        schemaGroup: {
          $cond: [
            {
              $eq: [
                { $type: "$schema_version" },
                "missing"
              ]
            },
            "v1",
            { $toString: "$schema_version" }
          ]
        }
      }
    },
    {
      $group: {
        _id: "$schemaGroup",
        docs: { $sum: 1 }
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray()
);
~~~

Expected output in a clean lab:

~~~text
v1: 1
2:  1
3:  1
~~~

On documents with `null` version, `$toString` returns `null` and groups them into an error/other bucket, so production reporting should classify invalids explicitly.

### 25.7. Running the Normalization Aggregation

Use the pipeline from **Section 14** to map city, rent, and `publishedAt` into canonical fields. Section 14 filters **cityCode HCM**, returning only v1 and v2 in the base lab.

### 25.8. Source Remains Unchanged After Read-Only Pipeline

Verify:

~~~javascript
printjson(
  listings.find(
    {
      _id: "b425-v1",
      labTag: "evolution425-v1"
    },
    {
      _id: 1,
      rent_vnd: 1,
      city: 1,
      schema_version: 1,
      pricing: 1
    }
  ).toArray()
);
~~~

The v1 document still has `rent_vnd` and `city`, with no `pricing` created from running the aggregation read.

### 25.9. Adding an Intentionally Malformed Fixture

**Optional**, lab only:

~~~javascript
listings.replaceOne(
  {
    _id: "b425-invalid",
    labTag: "evolution425-v1"
  },
  {
    _id: "b425-invalid",
    labTag: "evolution425-v1",
    schema_version: 3,
    tenant_id: "tenant-001",
    title: "Intentionally malformed data",
    pricing: {
      monthly: {
        amount: "23000000", // String with wrong BSON type
        currency: "VND"
      }
    },
    address: { city_code: "HN" },
    publication: {
      status: "PUBLISHED",
      published_at: ISODate("2026-01-17T09:00:00Z")
    }
  },
  { upsert: true }
);
~~~

Having `schema_version=3` **does not make this document valid**. The Java reader must reject it because `pricing.monthly.amount` is not `Decimal128`.

### 25.10. Inspecting Malformed Data with `$type`

~~~javascript
printjson(
  listings.aggregate([
    {
      $match: {
        labTag: "evolution425-v1",
        schema_version: 3
      }
    },
    {
      $project: {
        amountType: {
          $type: "$pricing.monthly.amount"
        }
      }
    }
  ]).toArray()
);
~~~

With the invalid fixture added:

~~~text
b425-v3:      amountType = decimal
b425-invalid: amountType = string
~~~

Never use **`$toDecimal`** to silently treat a malformed string as valid v3; that alters the data contract.

## 26. Read-Repair Only for Practicing Upgrading One Lab Document

### 26.1. Goal

Suppose a learner wants to upgrade **b425-v1** to v3 directly in the lab collection. Run this only after understanding:

- This is a **write operation**.
- It alters the raw document structure.
- Concurrent writers in the lab must be paused or protected by CAS.
- Production requires a migration framework/runbook, not raw copy-pasted scripts.

### 26.2. Upgrading v1 to v3 with a Narrowly Filtered Update

**Run only in the lab database and when `b425-v1` has not been altered by other exercises:**

~~~javascript
const lab = db.getSiblingDB(
  "mongo_evolution_lab_425"
);
const listings = lab.getCollection(
  "rental_listings_425"
);

const result = listings.updateOne(
  {
    _id: "b425-v1",
    labTag: "evolution425-v1",
    tenant_id: "tenant-001",
    schema_version: { $exists: false },
    rent_vnd: NumberLong("12500000"),
    city: "HCM",
    active: true,
    created_at: ISODate("2026-01-15T09:00:00Z")
  },
  {
    $set: {
      schema_version: 3,
      pricing: {
        monthly: {
          amount: NumberDecimal("12500000.00"),
          currency: "VND"
        }
      },
      address: { city_code: "HCM" },
      publication: {
        status: "PUBLISHED",
        published_at: ISODate("2026-01-15T09:00:00Z")
      }
    },
    $unset: {
      rent_vnd: "",
      city: "",
      active: "",
      created_at: ""
    }
  }
);

printjson(result);
~~~

The filter includes the original values of the transformed fields. If the document changed, **matchedCount is 0** and nothing writes. This demonstrates **conditional migration**, not full CAS with a universally maintained **revision**.

### 26.3. Why Not `replaceOne` by `_id` Alone?

A replacement document built only from canonical read-model fields can drop:

- `labTag`.
- Tenant authorization metadata.
- Domain data omitted from the read model.
- Fields recently added by another writer.
- Type metadata or fields used by indexes/queries.

A **targeted update** with tight predicates narrows the blast radius, yet production still needs migration reviews and concurrency controls.

### 26.4. What Happens on Re-Run?

After migration, `b425-v1` has `schema_version=3` and no `rent_vnd`. On the next run, **schema_version: { $exists:false }** does not match.

This is a **lab-level idempotent no-op**. It does not mean every conditional migration is automatically idempotent: operations that add money or append to arrays must be proven separately.

### 26.5. Restoring Initial Lab Data

To return to the original v1/v2/v3 fixtures, **re-run the seed script in Section 25.2**. The seed replaces only the lab's `_id`s. Never run `$unset` or drops against real application documents.

### 26.6. Stronger Production Requirements

Production needs:

- Unified revision/optimistic locking.
- Source field validation.
- Conflict observability.
- Idempotency.
- Rate limiting.
- Checkpointed migrations.
- Rollback/recovery plans.
- Audits of old writers.
- Separation of authorization from update control.

## 27. Unmarked Schema v1: When to Keep vs. Upgrade?

### 27.1. Keeping Legacy Support

Appropriate when:

- Old records are rarely read.
- v1 field semantics remain clear.
- No migration window is available yet.
- No severe query/index problems exist.

Long-term maintenance still has costs:

- Multiple code branches.
- Multiple indexes.
- Harder analytics/sorting.
- Exposure to unknown values.

### 27.2. Stamping Version Before Changing Shape?

A migration can add `schema_version:1` to valid v1 documents to distinguish accidental missing markers from legacy records. However:

- Never stamp `1` onto every document missing the field without validating its shape.
- Account for old writers continuing to insert unmarked documents.
- Update detection logic if both “missing” and explicit `1` represent v1.

### 27.3. Never Guess by Field Existence Once Explicit Markers Exist

Wrong:

~~~java
if (raw.containsKey("pricing")) {
    return readV3(raw);
}
~~~

if a v2 document temporarily dual-writes `pricing` to support app v3. It would be misclassified as v3 despite having `schema_version=2`.

Prefer explicit markers; shape detection is strictly a **contracted legacy fallback**.

## 28. Distinguishing Schema Upgrades from Business Semantic Changes

### 28.1. Semantics-Preserving Rename

~~~text
city -> location.city_code
~~~

is a structural rename if both use the exact same city code table.

### 28.2. Split/Merge Can Alter Meaning

~~~text
address: "123 Nguyen Van A, HCM"
    ->
address: {
  street: "...",
  city_code: "HCM"
}
~~~

If the old `address` was unstandardized free text, splitting into street/city can be **inaccurate**. Readers need a verified parser or must return “unresolved” and route to a repair queue.

### 28.3. Enum Migration

~~~text
v1 active boolean
   ->
v2 status PUBLISHED/DRAFT
   ->
v3 publication.status
~~~

If v1 `false` represented multiple causes, boolean→enum mapping loses information. Business policies, auxiliary fields, or manual migration are required.

### 28.4. Monetary Conversions

Converting:

~~~text
12500000 VND (Int64)
    ->
12500000.00 VND (Decimal128)
~~~

is a safe numeric representation change. Converting VND to USD is a **business transformation** requiring exchange rates and timestamps, not a pure schema migration.

## 29. Test Matrix Across Versions and App Releases

### 29.1. Document Fixtures

| Fixture | Marker | Rent Type | City Path | Expected |
| --- | --- | --- | --- | --- |
| Valid v1 | missing | Int64 | `city` | Canonical OK |
| Valid v2 | 2 Int32 | Decimal128 | `location.city_code` | Canonical OK |
| Valid v3 | 3 Int32 | Decimal128 | `address.city_code` | Canonical OK |
| Null version | null | Any | Any | Invalid |
| Future version | 4 | Any | Any | Unsupported |
| String marker | "3" | Any | Any | Invalid |
| Missing rent | 3 | missing | `address.city_code` | Invalid |
| Wrong rent type | 3 | String | `address.city_code` | Invalid |
| Unknown status | 3 | Decimal128 | `address.city_code` | Invalid |
| Negative price | 3 | Decimal128 | `address.city_code` | Invalid |
| Currency USD | 3 | Decimal128 | `address.city_code` | Invalid per lab contract |
| Missing tenant | 3 | Decimal128 | `address.city_code` | Invalid |

### 29.2. App Compatibility Cases

Verify:

- App R2 reads v1/v2.
- App R3 reads v1/v2/v3.
- Old readers never encounter v3 during writer rollout.
- Restored backups containing v1/v2 are readable by current apps.
- Post-cutover writers create only v3.
- Backfills do not break read paths during updates.

### 29.3. Query Cases

- Searching HCM returns v1 + v2, excluding v3 HN.
- Searching HN returns v3.
- Only current tenant records are visible.
- Canonical timestamp sorting works properly.
- Pagination remains stable with appropriate keysets/sorts.
- Indexes match active query shapes.
- Query counts do not miss v1/v2.

### 29.4. Read-Repair Cases

- Valid v1 repairs cleanly.
- Repairing the same document twice is a no-op on the second pass.
- CAS conflicts do not overwrite newer writes.
- Invalid documents are not repaired arbitrarily.
- Out-of-scope fields remain intact.
- Repair errors do not corrupt user-facing responses.

## 30. Performance When Maintaining Multiple Adapters

### 30.1. Adapter CPU Cost

Converting a small `Document` in Java usually costs far less than scanning a large collection, yet cannot be ignored at high throughput. Measure:

- Per-version conversion latency.
- v1/v2/v3 traffic ratio.
- Allocations/GC pressure.
- BSON deserialization overhead.

If v1 is only 0.1% of traffic, its adapter latency barely shifts overall p95, yet may impact p99 for cohorts holding legacy records.

### 30.2. Mixed-Path Queries Cost More

An `$or` query over three paths plus expression-based sorting often costs far more than the read adapter. Inspect:

- `docsExamined / nReturned`.
- `keysExamined`.
- Execution plan.
- Index footprint.
- CPU/disk load.
- p50/p95/p99 per query type.

### 30.3. Canonical Field to Support Search

When search gets too complex, you can add **one stable field** across all stored versions:

~~~javascript
{
  search_city_code: "HCM"
}
~~~

and backfill it. However, writers must then keep this field synchronized with `address`/`location`/`city`; otherwise it becomes a stale secondary source of truth.

### 30.4. Do Not Create Indexes Blindly

Three versions do not automatically mean three indexes are sufficient or optimal. Base index design on query selectivity, sorting, tenant isolation, write workload, space, and migration timeline.

### 30.5. Compare Before/After Fairly

A read adapter may save CPU while a new index increases write latency. Benchmarks require identical datasets, mixes, concurrency, warmup, driver settings, and SLOs.

## 31. Rollback, Restore, and Data from the Future

### 31.1. Why Code Rollback Is Hard After Switching Writers?

If the new app has written v3, rolling back the binary to an old app reading only v2 causes data failures.

~~~text
R1 reader: v1/v2
R2 writer: v3

Deploy R2 -> write v3 -> rollback R1
                      |
                      v
                 R1 cannot understand v3
~~~

Thus **binary rollback** is not **data rollback**.

### 31.2. Solutions

- Expand readers before writers.
- Ensure the rollback target binary can read v3.
- Use a feature flag to halt v3 writes when needed.
- Do not drop adapters prematurely.
- If v3→v2 down-conversion is required, prove losslessness and write a runbook.

### 31.3. Restoring Legacy Backups

Restoring a pre-migration snapshot brings v1/v2 back into the collection. Post-restore apps must still read them, or run migration/reconciliation **before reopening traffic**.

### 31.4. Offline Data

An offline writer/client might submit old-version documents after backfill finishes. Validate/transform at the ingest boundary or reject old versions per policy rather than letting legacy schemas reappear indefinitely.

## 32. Production Runbook for Schema-on-Read

### 32.1. Preparation

1. Inventory existing schema variants and actual BSON types.
2. Define versioned contracts per schema, especially money/enums/dates.
3. Identify stable fields for tenant/identity/authorization.
4. Design the canonical read model.
5. Implement adapters with invalid/unsupported handling.
6. Build fixtures from approved, PII-redacted data.
7. Define the query/index migration strategy.
8. Prepare backups and rollback plans.

### 32.2. Deploy Expanded Read Support

1. Roll out readers supporting v1/v2/v3.
2. Keep writers on the old schema until readers are fully compatible.
3. Monitor per-version read errors and latency.
4. Verify query coverage for legacy data.
5. Verify tenant isolation.

### 32.3. Writer Cutover

1. Confirm zero remaining old readers unable to handle v3.
2. Enable the v3 writer feature flag.
3. Monitor newly written documents by version.
4. Run canaries and diff data/responses.
5. Keep a kill switch to halt new writes if errors arise.

### 32.4. Migration/Backfill

1. Dry-run on staging with a representative dataset.
2. Backfill in batches with checkpoints.
3. Enforce CAS/idempotency against concurrent source updates.
4. Throttle IOPS/concurrency.
5. Track dead-letter/invalid counts.
6. Reconcile counts and values.
7. Prevent old writers from re-emitting legacy schemas.

### 32.5. Contract/Decommission

1. Stored v1/v2 count reaches 0 or covered by approved exceptions.
2. Unknown/invalid docs resolved.
3. APIs, tests, and backup restores no longer depend on old adapters.
4. Remove old indexes systematically.
5. Enable validation for the new schema where appropriate.
6. Archive migration audit logs and rollback policy.

## 33. Failure Modes and Responses

| Symptom | Likely Cause | Action |
| --- | --- | --- |
| v1 loads by `_id` yet missing from search | Query uses only v3 field | Multi-path query or backfill search key |
| v3 marker doc has null rent | Missing/malformed nested field | Invalid schema; never default price to 0 |
| Reads fail after new deploy | Converter lacks old schema support | Roll back compatible reader / fix adapter |
| Reads fail after code rollback | New writer already saved v3 | Expanded rollback reader / controlled write flag |
| Rent off by 1,000,000x | Confused VND vs. millions of VND | Fix business conversion contract |
| `BigDecimal` wrong/overflow | Coerced from Double/String | Exact `Decimal128` conversion and validation |
| `publishedAt` hours shifted | Confused UTC/timezone | Check BSON Date/`Instant`/`ZoneId` |
| Unknown enum becomes DRAFT | Wrong default | Fail explicitly on unsupported status |
| `schema_version:null` treated as v1 | Misused `$ifNull` | Use `$type` to isolate missing |
| Reader ignores v4 | Silently defaults to v3 | Fail closed + alert |
| Legacy fields lost after API save | Replaced canonical view | Separate read/write models; targeted Update |
| Read-repair loses user update | Stale document, missing CAS | Revision/source guard |
| v2 reappears after backfill | Old writer/mobile/offline client | Ingest version policy + monitoring |
| `$or` query slow | Unsuitable index paths | Explain, redesign query/backfill |
| Sort order wrong | Timestamp split across three paths | Canonical sort projection or backfill |
| Cross-tenant leak | Query missed tenant filter | Authenticated tenant predicate at DB |
| Read-repair spikes Change Stream | Migration writes emit events | Distinguish migration events & throttle |
| Cache returns stale price | Missing invalidation on update/repair | Versioned cache keys & invalidation |
| Migration reports 100% yet invalid remain | Counted v3 only | Reconcile unknown/null/bad schemas |
| Dropping adapter breaks backup restore | Legacy backup holds v1/v2 | Restore compatibility drills |
| New validator blocks old writer | Out-of-order rollout | Phase readers/writers/validation properly |
| Metric explosion | Labels include `_id`, `tenantId` | Bounded labels |
| Backfill causes high disk latency | Batch/concurrency too high | Throttle + capacity planning |

## 34. Hands-On Exercises

### Exercise 1 — Schema Identification

A collection has v1 documents lacking `schema_version`, v2 with `schema_version=2`, and v3 with `schema_version=3`. Why is a historical contract needed before treating a missing marker as v1?

### Exercise 2 — Version Types

Distinguish `schema_version=3`, `revision=17`, app release `4.8.2`, and MongoDB server version. When updating a title, which field should change?

### Exercise 3 — Canonical DTO

Design `ListingView` with ID, tenant, title, `Money`, `cityCode`, `status`, and `publishedAt`. Why does the read model not have to match stored BSON?

### Exercise 4 — v1 Mapping

Convert `rent_vnd NumberLong(12500000)` to `BigDecimal` VND. Why avoid multiplying/dividing by 1,000,000 unless the contract requires it?

### Exercise 5 — v2 Mapping

From `monthly_rent_vnd Decimal128`, `location.city_code`, and `status`, construct a `ListingView` with canonical fields.

### Exercise 6 — v3 Mapping

Trace paths `pricing.monthly.amount`, `pricing.monthly.currency`, `address.city_code`, and `publication.status` inside the Java adapter.

### Exercise 7 — Missing vs. Null

How do you distinguish missing `schema_version` from `schema_version:null` via `$type`/`$exists`? Why avoid `null` equality to identify v1?

### Exercise 8 — Future Version

A document has `schema_version=4` while the reader only supports up to 3. What should the reader do? Why not guess v3?

### Exercise 9 — Wrong BSON Type

v3 `pricing.monthly.amount` is String `"23000000"` instead of `Decimal128`. How do you handle it without hiding writer bugs?

### Exercise 10 — Currency

v1/v2 default to VND while v3 has `currency=USD`. What should this lesson's adapter do, and why not convert to VND using today's exchange rate?

### Exercise 11 — Enum

If v1 `active=false` could mean DRAFT, BLOCKED, or ARCHIVED, is mapping `false→DRAFT` safe? Propose a policy.

### Exercise 12 — Date

Compare BSON `Date` with `Instant`. Why not use `LocalDateTime` and assume a timezone was stored in BSON?

### Exercise 13 — Adapter

Write the switch dispatching v1/v2/v3 and throwing on unknown versions. Why is `if (has pricing)` insufficient during dual-writes?

### Exercise 14 — v1 Unit Test

Construct a legacy `org.bson.Document` in Java, run `VersionedListingReader`, and assert rent, city, status, and `publishedAt`.

### Exercise 15 — Negative Unit Tests

Test null marker, String marker, unknown version, missing nested fields, and negative price. How should `InvalidSchema` be distinguished from `UnsupportedVersion`?

### Exercise 16 — Integration

Seed raw BSON v1/v2/v3 into a MongoDB Testcontainer. Why must you re-read raw BSON even after `Document→DTO` unit tests pass?

### Exercise 17 — Tenant Isolation

An API reads a document by `_id` without filtering `tenant_id`. Why is a correct read adapter still insecure?

### Exercise 18 — Multi-Version Query

Write a MongoDB query finding `cityCode` HCM across v1/v2/v3 using `$or` and proper schema markers.

### Exercise 19 — Query Performance

If an `$or` query scans too many documents despite low `nReturned`, how do you use `explain` and design indexes?

### Exercise 20 — Sort

v1 uses `created_at`, v2 uses `published_at`, v3 uses `publication.published_at`. How do you sort by canonical `publishedAt` before pagination?

### Exercise 21 — Aggregation

Write a `$switch` computing `canonical_city` from three paths. When do you use `$type` to isolate missing markers?

### Exercise 22 — `$toDecimal`

Why can `$toDecimal` in aggregation make malformed Strings appear valid? When is strict validation needed instead of coercion?

### Exercise 23 — Read-Only

Run a pipeline with only `$match/$set/$project/$sort`. Does the source document automatically upgrade to v3? Which aggregation stages cause side effects?

### Exercise 24 — Read-Repair

Compare in-memory transformation with lazy read-repair. When should you avoid writing to the database from the read path?

### Exercise 25 — CAS

A reader loads `revision=7`, while another writer bumps `revision=8`. Which update predicate prevents read-repair from overwriting fresh data?

### Exercise 26 — `schema_version` vs. `revision`

Two writes happen under `schema_version=2`. Why is filtering solely by `schema_version=2` insufficient against lost updates?

### Exercise 27 — Idempotency

Design a v1→v3 read-repair safe to retry after network errors without incrementing rent or dropping unrelated fields.

### Exercise 28 — Cold Documents

20% of documents are read frequently while 80% are rarely read. Why does read-repair fail to move the entire collection to v3?

### Exercise 29 — Expand–Migrate–Contract

Sequence deploying compatible readers, new writers, backfill, verifying zero legacy schemas, and removing adapters.

### Exercise 30 — Rolling Deploy

At a moment in time, app R2 reads only v1/v2 while app R3 writes v3. Where does the system fail? How should the rollout order be fixed?

### Exercise 31 — Restore Rollback

After all writers are v3, you restore a backup holding v1/v2. Which tests/adapters must remain so the system can serve it?

### Exercise 32 — Unknown Fields

A v1 document has `legacy_note` and `owner_metadata` absent from `ListingView`. Why must `ListingView` never be used as a replacement document?

### Exercise 33 — Lab Seed

Run Section 25.2 in `mongosh`. Inspect all three documents, their BSON types, and the missing `schema_version` on `b425-v1`.

### Exercise 34 — Lab Query

Run the HCM query in Section 25.5. Why does it return `b425-v1` and `b425-v2` while excluding `b425-v3`?

### Exercise 35 — Invalid Fixture

Insert `b425-invalid` per Section 25.9. Write a Java unit/integration test confirming the reader refuses to treat a String rent amount as valid.

### Exercise 36 — Lab Write-Back

In the lab only, run the v1→v3 update from Section 26.2. Explain `matchedCount`, source predicates, and why re-running is a no-op.

### Exercise 37 — Index Cleanup

Once 100% of stored documents are v3, what must you verify before dropping v1/v2 indexes?

### Exercise 38 — Monitoring

Design a dashboard displaying stored-doc counts for v1/v2/v3/unknown, reads by version, invalid/unsupported errors, adapter latency, read-repair conflicts, and backfill progress.

### Exercise 39 — Schema Validation

During rolling deployment, a validator accepts only v3 while old apps still write v2. What happens and in what order must changes occur?

### Exercise 40 — Synthesis

An application has 15 million documents across four schemas, uses rolling deployments, searches by city/price, serves multi-tenant APIs, and enforces strict p99 SLOs. Design the canonical reader, query/index transition, adapter test matrix, rollout, CAS backfill, observability, rollback, and contract phase.

## 35. References

- MongoDB Manual — [Documents](https://www.mongodb.com/docs/manual/core/document/).
- MongoDB Manual — [BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/).
- MongoDB Manual — [Schema Design Patterns](https://www.mongodb.com/docs/manual/data-modeling/design-patterns/).
- MongoDB Manual — [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/).
- MongoDB Manual — [Specify Validation Level for Existing Documents](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-level/).
- MongoDB Manual — [Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/).
- MongoDB Manual — [Query Embedded Documents](https://www.mongodb.com/docs/manual/tutorial/query-embedded-documents/).
- MongoDB Manual — [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/).
- MongoDB Manual — [$switch](https://www.mongodb.com/docs/manual/reference/operator/aggregation/switch/).
- MongoDB Manual — [$type Aggregation Expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/type/).
- MongoDB Manual — [$convert](https://www.mongodb.com/docs/manual/reference/operator/aggregation/convert/).
- MongoDB Manual — [Update Documents](https://www.mongodb.com/docs/manual/tutorial/update-documents/).
- MongoDB Manual — [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/).
- MongoDB Manual — [Indexes](https://www.mongodb.com/docs/manual/indexes/).
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/).
- MongoDB Manual — [Change Streams](https://www.mongodb.com/docs/manual/changeStreams/).
- Spring Data MongoDB Reference — [Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html).
- Spring Data MongoDB Reference — [Custom Conversions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/custom-conversions.html).
- Spring Data MongoDB Reference — [MongoTemplate](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-api.html).
- MongoDB Java Driver — [Work with BSON Documents](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/documents/).

**Conclusion:** In MongoDB, a collection can hold **multiple schema versions concurrently** during data evolution. To read safely, applications must **detect versions per contract, convert each BSON shape into a canonical read model, validate data types, and preserve business semantics**. Transforming on read **does not mutate the underlying document**; upgrading stored data requires a **conditional backfill or read-repair process with concurrency guards, monitoring, and a rollback plan**. Moreover, **reading a document by `_id` does not guarantee multi-version search/sort/index correctness**: queries must cover old/new paths or rely on migrated canonical fields. The durable operational strategy is **expand readers first, switch writers second, migrate data under control, verify thoroughly, and contract legacy support last**, ensuring every data version is interpreted accurately without lost updates or business drift.
