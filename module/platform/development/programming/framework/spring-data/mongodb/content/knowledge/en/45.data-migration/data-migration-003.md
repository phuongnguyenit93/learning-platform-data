# Renaming Fields, Converting BSON Types, and Adding Default Values

In MongoDB, documents within the same collection can have different structures. When a Spring Data MongoDB application changes its data model, existing records **do not automatically change** to match the new Java class. Data migration transforms documents into the structure expected by the new application version while preserving data and keeping the system operational during the transition.

This lesson practices three common operations: **renaming fields**, **converting BSON types**, and **adding default values**. We will use both MongoDB commands and `MongoTemplate`, look at how `Decimal128` maps in Spring Data MongoDB, and then verify and deploy the migration safely.

## 1. Problem Statement and Target Data Structure

Suppose the `customers` collection currently contains documents like this:

```javascript
{
  _id: ObjectId("66d000000000000000000001"),
  fullName: "Nguyễn Lan",
  creditLimit: "1250.50",
  createdAt: ISODate("2024-07-01T08:00:00Z")
}
```

The new application version wants:

| Field | Before migration | After migration | Meaning |
| --- | --- | --- | --- |
| Display name | `fullName` | `displayName` | Align field name with the new model |
| Credit limit | `creditLimit` as BSON String | `creditLimit` as BSON Decimal128 | More accurate decimal arithmetic |
| Activation status | `isActive` may be missing | `isActive` as Boolean | Explicit default value for legacy data |

Desired document after transformation:

```javascript
{
  _id: ObjectId("66d000000000000000000001"),
  displayName: "Nguyễn Lan",
  creditLimit: NumberDecimal("1250.50"),
  isActive: false,
  createdAt: ISODate("2024-07-01T08:00:00Z")
}
```

**Business assumption for this example:** legacy customers without `isActive` are considered inactive (`false`). In a real system, you must confirm the meaning of the default value with business stakeholders before updating; never pick `false` or `true` simply because it is convenient in Java.

The migration also needs to handle inconsistent data:

- Documents that already have `displayName`, or have **both** `fullName` and `displayName`.
- `creditLimit` that is already Decimal128, a valid numeric string, an invalid string like `"unknown"`, `null`, or completely absent.
- `isActive` that does not exist yet, is already `true`/`false`, or is explicitly stored as `null`.

Never run an unconditional update across all records, as it can overwrite valid values or destroy data that requires manual resolution.

## 2. Inspecting Data Before Modifying It

Before running a migration, check backups/recovery readiness and collect statistics on data groups using `mongosh`:

```javascript
const customers = db.getCollection("customers");

// Safe to rename because the new name does not exist yet.
customers.countDocuments({
  fullName: { $exists: true },
  displayName: { $exists: false }
});

// Requires manual conflict handling: both old and new names exist.
customers.countDocuments({
  fullName: { $exists: true },
  displayName: { $exists: true }
});

// Credit limit values currently stored as strings.
customers.countDocuments({ creditLimit: { $type: "string" } });

// Actual BSON type distribution of the creditLimit field.
customers.aggregate([
  {
    $group: {
      _id: { $type: "$creditLimit" },
      count: { $sum: 1 }
    }
  }
]);

// Distinguish missing field from present field with null value.
customers.countDocuments({ isActive: { $exists: false } });
customers.countDocuments({ isActive: { $type: "null" } });
```

The `$type` check is important because BSON distinguishes `string`, `int`, `long`, `double`, and `decimal`. The same value may look like a number when displayed, yet be stored under different types. For currency or credit limits requiring decimal precision, use `Decimal128` and `BigDecimal`; converting from `double` cannot recover precision already lost earlier.

## 3. Renaming Fields with `$rename`

MongoDB supports `$rename` in standard update statements:

```javascript
const renameResult = db.customers.updateMany(
  {
    fullName: { $exists: true },
    displayName: { $exists: false }
  },
  {
    $rename: { fullName: "displayName" }
  }
);

printjson({
  matched: renameResult.matchedCount,
  modified: renameResult.modifiedCount
});
```

The `displayName: { $exists: false }` condition is critical: if the target field already exists, `$rename` can overwrite the target value. When a document has both names, investigate whether it is duplicate data, newer data, or a business conflict before deciding which value to keep.

`$rename` does not create a new value when the source field is absent. It works for renaming top-level fields or regular nested field paths; it does **not** directly rename fields inside array elements. For arrays of subdocuments, design a dedicated transformation, such as using `$map` in an aggregation pipeline.

In Spring Data MongoDB, `MongoTemplate` provides the corresponding API:

```java
Query query = Query.query(
    Criteria.where("fullName").exists(true)
        .and("displayName").exists(false)
);

Update update = new Update().rename("fullName", "displayName");
UpdateResult result = mongoTemplate.updateMulti(query, update, "customers");
```

This operates directly on the collection. Renaming a property in a Java class or adding `@Field("displayName")` **does not automatically rename** the field stored in the database.

## 4. Converting BSON String to Decimal128

MongoDB provides the `$toDecimal` and `$convert` operators. `$toDecimal` is concise when source data is guaranteed valid, but a single unconvertible value can cause the update command to fail. `$convert` allows specifying `onError` and `onNull` rules.

The example below processes only documents where `creditLimit` is a BSON String; valid strings become Decimal128, while invalid strings are **preserved** for investigation:

```javascript
const convertResult = db.customers.updateMany(
  { creditLimit: { $type: "string" } },
  [
    {
      $set: {
        creditLimit: {
          $convert: {
            input: "$creditLimit",
            to: "decimal",
            onError: "$creditLimit",
            onNull: "$creditLimit"
          }
        }
      }
    }
  ]
);

printjson({
  matched: convertResult.matchedCount,
  modified: convertResult.modifiedCount
});
```

This is an **aggregation pipeline update**: the update argument is an array of stages, where `"$creditLimit"` is an expression referencing the stored field value. For example, `"1250.50"` becomes `NumberDecimal("1250.50")`. For `"unknown"`, the `onError` expression returns the original string; after the migration, that record still requires handling.

Do not use `onError: 0` or `onError: null` just to make the command finish, as that destroys the original information. When source data contains currency symbols, irregular whitespace, or locale formatting like `"1.250,50"`, define cleaning and validation rules before converting. Converting a number incorrectly to Decimal128 is more dangerous than keeping the invalid data for later handling.

With Spring Data MongoDB, you can use the MongoDB Java Driver API via `MongoTemplate.getCollection(...)` when raw pipeline syntax is needed:

```java
Document convert = new Document("$convert",
    new Document("input", "$creditLimit")
        .append("to", "decimal")
        .append("onError", "$creditLimit")
        .append("onNull", "$creditLimit")
);

List<Document> pipeline = List.of(
    new Document("$set", new Document("creditLimit", convert))
);

UpdateResult result = mongoTemplate.getCollection("customers").updateMany(
    new Document("creditLimit", new Document("$type", "string")),
    pipeline
);
```

This direct collection call uses **actual BSON field names**. It does not automatically apply entity property mapping rules or `MappingMongoConverter` lifecycle events; you must specify the exact field names stored in the database.

### Mapping Decimal128 in Entities

When the application starts writing the new type, the entity should explicitly express storing `BigDecimal` as BSON Decimal128:

```java
import java.math.BigDecimal;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document("customers")
public class Customer {
    @Id
    private String id;

    @Field("displayName")
    private String displayName;

    @Field(value = "creditLimit", targetType = FieldType.DECIMAL128)
    private BigDecimal creditLimit;

    @Field("isActive")
    private Boolean active;

    // Constructor, getters, and setters omitted.
}
```

Simply declaring `BigDecimal` is not enough to guarantee MongoDB data will be written as Decimal128: converter configuration and `@Field(targetType = FieldType.DECIMAL128)` must be considered together. This annotation affects application mapping; it **does not retroactively convert** existing documents. While invalid strings remain in the database, reading into a `BigDecimal` property may fail conversion, so you must verify and fix those records before requiring all read paths to use the new entity.

## 5. Adding Default Values for Missing Fields

Default values for legacy records should be written conditionally:

```javascript
const defaultResult = db.customers.updateMany(
  { isActive: { $exists: false } },
  { $set: { isActive: false } }
);

printjson({
  matched: defaultResult.matchedCount,
  modified: defaultResult.modifiedCount
});
```

This command only updates documents that **do not yet have** `isActive`. Documents already storing `true` or `false` remain untouched. Documents with `isActive: null` also remain untouched, because `null` and an absent field may represent two different business states.

Equivalent in `MongoTemplate`:

```java
Query query = Query.query(Criteria.where("isActive").exists(false));
Update update = Update.update("isActive", false);

UpdateResult result = mongoTemplate.updateMulti(
    query, update, "customers"
);
```

If business rules dictate that `null` must also receive a default value, separately inspect documents with `{ isActive: { $type: "null" } }` and run an approved update for that group. Do not use `{ isActive: null }` when you only want to match explicit null values, because that filter also matches documents missing the field.

When creating new documents, the application must write `isActive` according to business rules. Backfilling old data does not automatically provide defaults for future inserted documents.

## 6. Organizing Migrations in Spring Data MongoDB

One implementation approach is placing the logic in a migration class invoked in a controlled manner from an operational tool or a one-off task. The snippet below combines the three updates explained above:

```java
import java.util.List;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public final class CustomerDataMigration {
    private final MongoTemplate mongoTemplate;

    public CustomerDataMigration(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public void migrate() {
        UpdateResult renamed = mongoTemplate.updateMulti(
            Query.query(
                Criteria.where("fullName").exists(true)
                    .and("displayName").exists(false)
            ),
            new Update().rename("fullName", "displayName"),
            "customers"
        );

        Document convert = new Document("$convert",
            new Document("input", "$creditLimit")
                .append("to", "decimal")
                .append("onError", "$creditLimit")
                .append("onNull", "$creditLimit")
        );
        UpdateResult converted = mongoTemplate
            .getCollection("customers")
            .updateMany(
                new Document("creditLimit", new Document("$type", "string")),
                List.of(new Document("$set",
                    new Document("creditLimit", convert)))
            );

        UpdateResult defaulted = mongoTemplate.updateMulti(
            Query.query(Criteria.where("isActive").exists(false)),
            Update.update("isActive", false),
            "customers"
        );

        System.out.printf(
            "Renamed=%d; converted=%d; defaulted=%d%n",
            renamed.getModifiedCount(),
            converted.getModifiedCount(),
            defaulted.getModifiedCount()
        );
    }
}
```

For production use, you must add a **coordination lock or migration version tracking mechanism**, full logging and metrics, a retry policy, and progress monitoring. Avoid running uncontrolled bulk update tasks from `@PostConstruct` on every application instance: multiple instances may start concurrently, and large migrations can delay deployment or generate unexpected write load.

The three commands above **do not form an atomic transaction across the whole collection**. MongoDB guarantees atomicity for writes on individual documents, but if the process stops between steps, the collection may temporarily contain both data shapes. The system must tolerate transitional states or follow a phased deployment process; do not wrap an entire large collection in a long-running transaction just to apply a backfill.

## 7. Verifying Results and Re-runnability

After the migration, run verification queries independent of `modifiedCount`:

```javascript
// Are there any documents left with the old name and no new name?
db.customers.countDocuments({
  fullName: { $exists: true },
  displayName: { $exists: false }
});

// Are there documents containing both names? Requires manual reconciliation.
db.customers.countDocuments({
  fullName: { $exists: true },
  displayName: { $exists: true }
});

// Remaining strings are unconvertible or unprocessed values.
db.customers.find(
  { creditLimit: { $type: "string" } },
  { displayName: 1, creditLimit: 1 }
);

// Is the default field still missing anywhere?
db.customers.countDocuments({ isActive: { $exists: false } });

// Observe BSON types after conversion.
db.customers.aggregate([
  { $group: { _id: { $type: "$creditLimit" }, count: { $sum: 1 } } }
]);
```

For a valid sample dataset, re-running the steps should preserve the result: already-renamed fields are not renamed again; Decimal128 values do not match the String type filter; documents with `isActive` do not match the missing-field filter. Failed conversion strings remain preserved and can be retried in subsequent runs; the count of this error group should be tracked until resolved.

A useful integration test suite should construct these cases:

| Initial data | Result to verify |
| --- | --- |
| Only `fullName` | Renamed to `displayName` with no content lost |
| Both `fullName` and `displayName` | Does not overwrite `displayName`; reports conflict group |
| `creditLimit: "1250.50"` | BSON type after migration is `decimal` |
| `creditLimit: "unknown"` | Original string is preserved and counted for handling |
| `creditLimit` already Decimal128 | Not converted again |
| Missing `isActive` | Adds Boolean `false` per business assumption |
| `isActive: true` or `isActive: null` | Not unintentionally modified |
| Running migration a second time | Valid documents do not change state |

In particular, compare **document counts before/after**, critical business fields, and a known sample set rather than relying solely on commands returning without exceptions. `matchedCount` and `modifiedCount` are progress indicators, not proof that all data conforms to the schema.

## 8. Deploying on a Live System

When multiple application versions run concurrently during deployment, the practical sequence is typically:

1. **Inspect and prepare:** gather statistics on BSON types, field names, null values, and conflict groups; take a restorable backup and choose an appropriate window.
2. **Ensure compatibility:** the transitional application version can read both `fullName` and `displayName`, and handles unconverted `creditLimit` values. Clearly define when writing the old shape stops.
3. **Run monitored migration:** favor precise filters; for large collections, split into batches by `_id` or stable ranges, throttle load, and log processed/error counts.
4. **Reconcile:** verify data, fix malformed strings and conflicting field names, and check queries and calculations on Decimal128.
5. **Cut over completely to the new schema:** update entities/repositories, indexes, and schema validation rules; remove legacy compatibility logic once all readers and writers have transitioned.

If application queries use `displayName`, evaluate a corresponding index after measuring performance:

```javascript
db.customers.createIndex({ displayName: 1 });
```

An index on `fullName` may still be needed by older application versions during the transition. Creating/dropping indexes, scanning collections, and updating large numbers of documents impact response times, I/O, replication lag, and storage capacity. Test on realistic datasets and monitor the system during each batch.

When rollback is needed, do not assume the three updates are completely reversible: renaming can later create conflicts, type conversion may alter the original representation, and adding `false` erases the information that "this field previously did not exist." A backup or pre-migration change log is the reliable basis for recovery.

## 9. Common Errors

| Error | Consequence | Prevention |
| --- | --- | --- |
| Running `$rename` when target field already exists | Can overwrite new values | Filter `$exists: false` and handle conflicting records separately |
| Using `$toDecimal` on unvalidated data | Invalid values cause the update to fail | Use `$convert` with `onError`, track invalid data |
| Treating `null` as a missing field | Overwrites a business state | Distinguish `$exists: false` and `$type: "null"` |
| Only changing `@Field` or Java types | Old documents still carry the old schema | Run data migration, verify actual BSON |
| Running huge updates at every instance startup | Load spikes, conflicts, hard to coordinate | Use a controlled migration runner or scheduled batches |
| Assuming multiple `updateMany` calls are a transaction | Data left in intermediate state | Design compatible deployments and safe re-runnable updates |

## 10. Practice Exercise

Create a test `customers` collection with at least six documents: single old name, two conflicting names, valid numeric string credit limit, invalid string, already-canonical Decimal128, and `isActive` as `null`. Execute the rename, type conversion, and default-filling steps sequentially using `mongosh` or `MongoTemplate`.

The result meets requirements when:

- All eligible documents are renamed to `displayName` without overwriting existing new names.
- Valid credit limit strings become BSON Decimal128; invalid strings are kept for investigation.
- Only documents missing `isActive` receive the agreed default.
- Verification queries accurately identify remaining records needing follow-up, and running the migration a second time does not corrupt valid data.

**Remember:** a successful migration is not just running `updateMany` without errors. It must correctly interpret legacy data semantics, constrain update targets, preserve error visibility, and prove that the resulting BSON structure matches Spring Data MongoDB expectations.
