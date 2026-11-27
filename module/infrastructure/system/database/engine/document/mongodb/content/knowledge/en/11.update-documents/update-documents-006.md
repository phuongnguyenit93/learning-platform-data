# Updating Nested Fields Without Accidentally Replacing Child Documents in MongoDB

In MongoDB, a document can contain multiple **embedded documents** (nested documents) and arrays. When only a small field needs to change—such as the city in a shipping address—the update command must target the exact **field path**. If you update the parent object itself, MongoDB replaces the entire child object and drops any fields omitted from the new payload.

For example, given the address:

~~~javascript
{
  address: {
    city: "Hanoi",
    district: "Ba Dinh",
    postalCode: "100000"
  }
}
~~~

To change **city** to **Da Nang** while keeping **district** and **postalCode**, use **$set** combined with **dot notation**:

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  { $set: { "address.city": "Da Nang" } }
);
~~~

If instead you write:

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  { $set: { address: { city: "Da Nang" } } }
);
~~~

then **address** is replaced by a new object containing only **city**. Both commands are valid; the difference lies in the **boundary of the assigned field**.

This lesson focuses on safely updating nested fields in MongoDB, from basic dot notation to array filters, concurrency guards, and building patches in Java.

## 1. Why Updating Child Documents Easily Causes Data Loss

A BSON document has a tree structure. Each field can hold a scalar value, a nested document, or an array.

~~~text
Collection: users
└── Document: _id = "U-1001"
    ├── fullName
    ├── profile
    │   ├── displayName
    │   ├── address
    │   │   ├── city
    │   │   ├── district
    │   │   ├── postalCode
    │   │   └── geo
    │   │       ├── lat
    │   │       └── lon
    │   └── preferences
    │       ├── language
    │       └── emailNotifications
    ├── contacts[]
    └── audit
        ├── version
        └── updatedAt
~~~

There are three distinct update levels:

| Path used with $set | Scope of assigned value | What can be lost |
| --- | --- | --- |
| **profile.address.city** | Only the city field inside address | Sibling fields of city are preserved |
| **profile.address** | Entire address document | district, postalCode, geo if omitted from the new object |
| **profile** | Entire profile document | address, preferences, and other profile fields omitted from the new object |

MongoDB does not automatically treat a JavaScript object inside **$set** as a field-by-field deep-merge patch. **Assigning an object replaces the value at the exact specified path**, regardless of whether that object is large or small.

## 2. Creating the Sample Dataset

The commands below use **mongosh** and a dedicated test database:

~~~javascript
use nested_update_lab

db.users.insertOne({
  _id: "U-1001",
  fullName: "Nguyễn Minh An",
  profile: {
    displayName: "Minh An",
    address: {
      city: "Hanoi",
      district: "Ba Dinh",
      postalCode: "100000",
      geo: {
        lat: 21.034,
        lon: 105.815
      }
    },
    preferences: {
      language: "vi",
      emailNotifications: true
    }
  },
  contacts: [
    {
      type: "home",
      phone: "0900000001",
      verified: true
    },
    {
      type: "work",
      phone: "0900000002",
      verified: false
    }
  ],
  audit: {
    version: 1,
    updatedAt: ISODate("2026-01-01T00:00:00Z")
  }
});
~~~

The example assumes the collection does not already contain a document with **_id = "U-1001"**. Re-running the insert command will raise a duplicate key error. In a test environment, you can delete just the sample document with **deleteOne({ _id: "U-1001" })** and re-insert it; there is no need to drop the entire collection.

Inspect the document:

~~~javascript
db.users.findOne({ _id: "U-1001" });
~~~

In this structure:

- **profile** is a nested document.
- **profile.address** is a deeper child document.
- **profile.address.geo** contains two coordinate fields.
- **contacts** is an array containing multiple embedded documents.
- **audit.version** is used to illustrate concurrent update control.

## 3. Updating a Single Child Field Using Dot Notation

**Dot notation** uses periods to express a path through fields of nested documents:

~~~text
profile.address.city
│       │       └── field to set
│       └── embedded document address
└── embedded document profile
~~~

Change the city:

~~~javascript
const result = db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: {
      "profile.address.city": "Da Nang"
    }
  }
);

printjson(result);
~~~

Read back the address after the update:

~~~javascript
db.users.findOne(
  { _id: "U-1001" },
  { _id: 0, "profile.address": 1 }
);
~~~

Resulting structure:

~~~javascript
{
  profile: {
    address: {
      city: "Da Nang",
      district: "Ba Dinh",
      postalCode: "100000",
      geo: {
        lat: 21.034,
        lon: 105.815
      }
    }
  }
}
~~~

Only **city** changes; the remaining fields of **address** and **profile** are untouched by **$set** on that leaf path.

### 3.1. Why Must the Path Name Be a String?

In a JavaScript object literal, field names containing dots must be enclosed in quotes:

~~~javascript
{
  $set: {
    "profile.address.city": "Da Nang"
  }
}
~~~

If you write:

~~~javascript
// Invalid JavaScript object literal syntax:
{
  $set: {
    profile.address.city: "Da Nang"
  }
}
~~~

JavaScript does not treat **profile.address.city** as a valid unquoted property key. MongoDB drivers accept the target field path as a **string path**, such as `"profile.address.city"`.

### 3.2. Updating Multiple Leaf Fields in One Operation

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: {
      "profile.address.city": "Ho Chi Minh",
      "profile.address.postalCode": "700000",
      "profile.preferences.language": "en"
    },
    $currentDate: {
      "audit.updatedAt": true
    },
    $inc: {
      "audit.version": 1
    }
  }
);
~~~

A single **updateOne** command modifies multiple fields on the **same document**, and MongoDB applies the write atomically at the document level. Untargeted fields remain intact.

Note: updating **city** and **postalCode** together does not automatically verify they form a valid geographic pair. **Atomicity** guarantees all-or-nothing execution of the write, while business validity checks belong in the application or schema validation.

## 4. When Does $set Replace an Entire Child Document?

MongoDB does not deep-merge objects automatically. Compare these two updates.

### 4.1. Setting the Leaf Field: Preserves Sibling Fields

Initial document:

~~~javascript
{
  profile: {
    address: {
      city: "Hanoi",
      district: "Ba Dinh",
      postalCode: "100000"
    },
    preferences: {
      language: "vi"
    }
  }
}
~~~

Update:

~~~javascript
{
  $set: {
    "profile.address.city": "Da Nang"
  }
}
~~~

Result:

~~~javascript
{
  profile: {
    address: {
      city: "Da Nang",
      district: "Ba Dinh",
      postalCode: "100000"
    },
    preferences: {
      language: "vi"
    }
  }
}
~~~

### 4.2. Setting the Entire address Field: Replaces the Whole address Value

Update:

~~~javascript
{
  $set: {
    "profile.address": {
      city: "Da Nang"
    }
  }
}
~~~

Result:

~~~javascript
{
  profile: {
    address: {
      city: "Da Nang"
    },
    preferences: {
      language: "vi"
    }
  }
}
~~~

The **district** and **postalCode** fields are removed because the new object omits them. **preferences** remains because the operation assigned **profile.address**, not all of **profile**.

### 4.3. Setting the Entire profile Field: Even Broader Impact

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: {
      profile: {
        address: {
          city: "Da Nang"
        }
      }
    }
  }
);
~~~

If this runs on the sample document, **profile.displayName** and **profile.preferences** are also lost. Recovering them afterward requires original source data or a backup.

Practical rule: **the deepest path assigned is the replacement boundary**. Construct paths down to the fields you intend to change; never pass a parent object into **$set** when the input is only a partial patch.

## 5. How $set Differs from replaceOne and Saving Entire Objects

Two common update mechanisms:

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  { $set: { "profile.address.city": "Da Nang" } }
);
~~~

and:

~~~javascript
db.users.replaceOne(
  { _id: "U-1001" },
  {
    fullName: "Nguyễn Minh An",
    profile: {
      address: { city: "Da Nang" }
    }
  }
);
~~~

The **replaceOne** command replaces the **entire document body** with the replacement document (retaining `_id` per replacement rules if `_id` is omitted). Fields missing from the replacement, such as **contacts**, **audit**, and **profile.preferences**, disappear from the document after replacement.

| API / operation | Replacement scope | Appropriate when |
| --- | --- | --- |
| **updateOne** + $set on leaf path | Field at the specified path | Updating a few fields |
| **updateOne** + $set on parent object | Entire parent object value | Intentionally replacing an entire subtree |
| **replaceOne** | Entire document | Supplying a complete, explicitly controlled replacement |
| **findOneAndUpdate** + $set | Specified fields | Updating and returning the before/after document |
| **findOneAndReplace** | Entire document | Replacing the whole document and returning before/after |

A similar risk occurs when an ORM/ODM or repository layer calls a **save** method to persist a partially loaded object. Depending on the library and API, `save` may perform a full-document replacement or overwrite fields with unexpected default/null values. Understand the exact API you invoke; never assume "save a DTO with three fields" equals "patch three fields".

## 6. Differences Between $set, $unset, and Assigning null

Suppose **profile.address.postalCode** exists.

### 6.1. Assigning null

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: {
      "profile.address.postalCode": null
    }
  }
);
~~~

The **postalCode** field still exists, holding a BSON **null** value.

### 6.2. Removing a Child Field

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  {
    $unset: {
      "profile.address.postalCode": ""
    }
  }
);
~~~

Now **postalCode** is gone from the document. These two queries return different results:

~~~javascript
db.users.find({
  "profile.address.postalCode": { $exists: true }
});

db.users.find({
  "profile.address.postalCode": { $exists: false }
});
~~~

The **$exists** condition distinguishes whether the field is present; a plain equality filter against **null** in MongoDB matches both null fields and missing fields.

### 6.3. Avoid Using $set on the Whole address to Delete One Field

If you only want to remove `postalCode`, use **$unset** on that path. Writing back an address object containing only `city` and `district` replaces the entire subtree and risks dropping new fields added by another system, such as **geo**.

For example, to delete only **profile.address.geo.lon**:

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  {
    $unset: {
      "profile.address.geo.lon": ""
    }
  }
);
~~~

Sibling fields such as **lat** are preserved.

## 7. Missing Paths, null Values, and Incompatible Types

Dot notation can create nested paths when intermediate components **do not yet exist** and MongoDB can construct the necessary objects.

Example document:

~~~javascript
{ _id: "U-2001", fullName: "Binh" }
~~~

Update:

~~~javascript
db.users.updateOne(
  { _id: "U-2001" },
  {
    $set: {
      "profile.address.city": "Hue"
    }
  }
);
~~~

When that document exists without a **profile** field, MongoDB creates the structure:

~~~javascript
{
  _id: "U-2001",
  fullName: "Binh",
  profile: {
    address: {
      city: "Hue"
    }
  }
}
~~~

However, if an intermediate component **already exists as a non-document type**, the operation will fail. For example:

~~~javascript
{
  _id: "U-2002",
  profile: {
    address: null
  }
}
~~~

Request:

~~~javascript
db.users.updateOne(
  { _id: "U-2002" },
  {
    $set: {
      "profile.address.city": "Hue"
    }
  }
);
~~~

Here **address** is null, so MongoDB cannot traverse through it like a regular embedded document. The same issue occurs when a field holds an incompatible string, number, or array. **Never rely on dot notation to auto-repair malformed data types.**

### 7.1. Update Only When the Intermediate Structure Has the Right Type

On standardized data, you can verify the type before updating:

~~~javascript
const result = db.users.updateOne(
  {
    _id: "U-2002",
    "profile.address": { $type: "object" }
  },
  {
    $set: {
      "profile.address.city": "Hue"
    }
  }
);

printjson(result);
~~~

If **matchedCount = 0**, either no document matched or the current structure did not meet the type condition. The application must decide whether to migrate, report a data error, or initialize a new object per business logic.

### 7.2. Intentionally Creating the Parent Object

If **address: null** is a valid state and business logic wants to initialize a new address, explicitly replace `address` with a complete object:

~~~javascript
db.users.updateOne(
  {
    _id: "U-2002",
    "profile.address": null
  },
  {
    $set: {
      "profile.address": {
        city: "Hue",
        district: "",
        postalCode: null
      }
    }
  }
);
~~~

Note that `{ "profile.address": null }` normally matches both null and missing fields. To target BSON null specifically, combine with `$type: "null"`. Replacing the entire `address` in this case is **intentionally initializing a new object**, unlike updating just the city of an existing address.

## 8. Updating Arrays Containing Embedded Documents

Simple dot notation is insufficient when a path traverses an array. If a document contains:

~~~javascript
{
  _id: "U-1001",
  contacts: [
    { type: "home", phone: "0900000001", verified: true },
    { type: "work", phone: "0900000002", verified: false }
  ]
}
~~~

the typical goal is to change **the phone of the contact with type = "work"**, while keeping **type** and **verified**.

### 8.1. Positional Operator $: First Matching Array Element

~~~javascript
db.users.updateOne(
  {
    _id: "U-1001",
    "contacts.type": "work"
  },
  {
    $set: {
      "contacts.$.phone": "0911111111"
    }
  }
);
~~~

The positional operator **$** represents **the first array element matching the query condition** in supported contexts. The **verified** field of that contact stays intact.

When filters involve multiple arrays, complex conditions, or multiple matching elements, positional **$** quickly becomes error-prone. Prefer **arrayFilters** in those cases.

### 8.2. Filtered Positional Operator $[identifier]

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: {
      "contacts.$[contact].phone": "0911111111"
    }
  },
  {
    arrayFilters: [
      { "contact.type": "work" }
    ]
  }
);
~~~

**$[contact]** selects elements in the **contacts** array satisfying **contact.type = "work"**. If multiple contacts match, all matching elements in the document are updated together.

If business rules allow only **one** contact per type, enforce that invariant in your write logic and data model. Update operators do not enforce uniqueness of `type` values inside an array.

### 8.3. All Positional Operator $[]: Every Element

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: {
      "contacts.$[].verified": false
    }
  }
);
~~~

**$[]** affects every element of the `contacts` array. It differs from **$[identifier]** because it applies no per-element filter.

### 8.4. Fixed Numeric Index

You can also target a specific index directly:

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: {
      "contacts.0.phone": "0922222222"
    }
  }
);
~~~

This updates the element at array index 0. Use this only when the application knows for certain that position carries fixed meaning. If the array can be reordered, appended to, or trimmed, a hardcoded index may edit the wrong contact.

### 8.5. Assigning an Entire Array Element Drops Child Fields

Compare:

~~~javascript
// Preserves verified and type of the contact at index 0.
db.users.updateOne(
  { _id: "U-1001" },
  { $set: { "contacts.0.phone": "0922222222" } }
);
~~~

with:

~~~javascript
// Replaces the entire contact object at index 0.
db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: {
      "contacts.0": {
        phone: "0922222222"
      }
    }
  }
);
~~~

The second command replaces the entire array element with an object containing only **phone**. The risk of losing **type** and **verified** is identical to replacing an entire embedded document.

### 8.6. Multi-Level Nested Arrays

Suppose an order has shipment groups, each containing multiple line items:

~~~javascript
{
  _id: "ORD-5001",
  shipments: [
    {
      shipmentId: "S-01",
      items: [
        { sku: "BOOK-01", quantity: 1, note: "Hardcover" },
        { sku: "PEN-02", quantity: 2, note: "Blue" }
      ]
    }
  ]
}
~~~

Update only **note** for item `BOOK-01` inside shipment `S-01`:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-5001" },
  {
    $set: {
      "shipments.$[shipment].items.$[item].note": "Gift wrap"
    }
  },
  {
    arrayFilters: [
      { "shipment.shipmentId": "S-01" },
      { "item.sku": "BOOK-01" }
    ]
  }
);
~~~

Two array filters pinpoint each nesting level. This keeps **quantity**, **sku**, and all non-matching shipments/items intact.

## 9. Standard Updates vs. Aggregation Pipeline Updates

MongoDB supports two update forms:

~~~javascript
// Update document with the $set operator.
db.users.updateOne(
  { _id: "U-1001" },
  { $set: { "profile.address.city": "Da Nang" } }
);
~~~

and:

~~~javascript
// Aggregation pipeline update.
db.users.updateOne(
  { _id: "U-1001" },
  [
    {
      $set: {
        "profile.address.city": "Da Nang"
      }
    }
  ]
);
~~~

In the second form, **$set** is an **aggregation stage**. In simple string assignments, the updated field outcome is identical. However, pipelines evaluate aggregation expressions and interpret values differently from standard update operators.

For example, if a string value starts with **$**, a pipeline interprets it as a field path expression. Use **$literal** when you want to assign the literal string:

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  [
    {
      $set: {
        "profile.displayName": {
          $literal: "$admin"
        }
      }
    }
  ]
);
~~~

In a standard update `{ $set: { "profile.displayName": "$admin" } }`, `"$admin"` is treated as a literal string value, not a field reference expression.

### 9.1. Explicitly Merging Objects with $mergeObjects

Sometimes an application needs to merge a new object with an existing object on the server. Aggregation pipelines can use **$mergeObjects**:

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  [
    {
      $set: {
        "profile.address": {
          $mergeObjects: [
            "$profile.address",
            {
              city: "Da Nang",
              postalCode: "550000"
            }
          ]
        }
      }
    }
  ]
);
~~~

This preserves other top-level fields inside **profile.address**, such as **district** and **geo**, assuming the existing value has a compatible object structure.

However, **$mergeObjects merges only one level of fields**. If the new object contains `geo: { lat: ... }`, the entire previous **geo** object is replaced by the new one and **lon** is lost. It is **not an arbitrarily deep recursive merge**.

For patches touching a few known fields, dot notation remains the most direct and predictable approach.

### 9.2. Avoid Updating Both Parent and Child in One Command

Do not write:

~~~javascript
// Conflicting update paths.
db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: {
      "profile.address": { city: "Hue" },
      "profile.address.postalCode": "530000"
    }
  }
);
~~~

These two paths overlap: one sets **profile.address**, while the other sets **postalCode** inside that same object. MongoDB will reject conflicting paths in a standard update.

Pick one clear level:

~~~javascript
// Update each leaf field.
db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: {
      "profile.address.city": "Hue",
      "profile.address.postalCode": "530000"
    }
  }
);
~~~

Or intentionally replace all of **profile.address** with a complete object when that is the genuine business requirement.

## 10. Dotted Paths vs. Field Names Containing Literal Dots

In normal schemas:

~~~javascript
{
  profile: {
    address: {
      city: "Hanoi"
    }
  }
}
~~~

The path **"profile.address.city"** traverses three levels of embedded documents.

However, supported MongoDB versions can also store **field names containing dots**, such as a top-level field literally named `"profile.address.city"`:

~~~javascript
{
  "profile.address.city": "Hanoi"
}
~~~

These two structures are **different**. In standard updates, dot notation is interpreted by default as a **nested path**, not a literal field name containing dots.

For special field names, MongoDB provides expressions such as **$getField** and **$setField** in supported versions. Example updating a literal top-level field named `"profile.address.city"`:

~~~javascript
db.specialRecords.updateOne(
  { _id: "R-01" },
  [
    {
      $replaceWith: {
        $setField: {
          field: "profile.address.city",
          input: "$$ROOT",
          value: "Da Nang"
        }
      }
    }
  ]
);
~~~

This sets a **top-level field with literal dots in its name**, rather than updating the nested `profile.address` object.

In standard application design, **avoid field names containing dots or starting with $** unless there is a compelling reason. Using clean field names with dot notation for embedded documents avoids confusion across drivers and import/export tools.

## 11. Building Patches Properly at the Application Layer

A frequent bug occurs when an API accepts partial JSON and forwards it straight into **$set**.

For example, a client sends an HTTP PATCH:

~~~json
{
  "profile": {
    "address": {
      "city": "Da Nang"
    }
  }
}
~~~

If the backend runs:

~~~javascript
const patch = {
  profile: {
    address: {
      city: "Da Nang"
    }
  }
};

db.users.updateOne(
  { _id: "U-1001" },
  { $set: patch }
);
~~~

then **the entire profile** is replaced by an object containing only **address.city**. **displayName**, **preferences**, **address.district**, and **address.geo** are wiped out.

### 11.1. Translating to Leaf-Path Patches

When the API has an explicit contract, construct the update document using known paths:

~~~javascript
const requestBody = {
  address: {
    city: "Da Nang"
  },
  preferredLanguage: "en"
};

const setFields = {};

if (requestBody.address?.city !== undefined) {
  setFields["profile.address.city"] =
    requestBody.address.city;
}

if (requestBody.preferredLanguage !== undefined) {
  setFields["profile.preferences.language"] =
    requestBody.preferredLanguage;
}

db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: setFields
  }
);
~~~

This maps the **city** input to an explicit leaf field. Never pass raw `requestBody` or parent objects directly into MongoDB.

Check **!== undefined** rather than truthiness so valid falsy values like **false**, **0**, or empty strings are not skipped. For **null**, decide per API contract whether to **assign BSON null** or **remove the field with $unset**; those two behaviors are distinct.

In production code, if zero fields require updating, return a no-op outcome at the application layer rather than sending an empty update command.

### 11.2. Never Construct Arbitrary Paths from Client Keys

Never let clients arbitrarily send:

~~~json
{
  "fieldPath": "audit.version",
  "value": 999
}
~~~

and pass **fieldPath** straight into **$set**. Without validation, clients can mutate internal fields, security attributes, or introduce structural conflicts.

Use an **allowlist** of modifiable fields:

~~~javascript
const allowedPaths = {
  city: "profile.address.city",
  postalCode: "profile.address.postalCode",
  language: "profile.preferences.language"
};

function buildUpdate(key, value) {
  const path = allowedPaths[key];

  if (!path) {
    throw new Error("Field is not allowed to be updated");
  }

  return {
    $set: {
      [path]: value
    }
  };
}
~~~

This preserves child document boundaries and enforces update permissions per the API contract.

### 11.3. JSON Merge Patch and JSON Patch Have Distinct Rules

Naming an endpoint HTTP **PATCH** does not make the backend deep-merge JSON automatically. Two common patch standards define different semantics:

- **JSON Merge Patch** describes object merging where `null` typically means deleting that member per specification.
- **JSON Patch** is a sequence of operations (`add`, `replace`, `remove`) targeting JSON pointers.

MongoDB **$set** does not automatically implement either specification. If an API accepts a specific patch format, the backend must interpret that spec accurately and translate it into appropriate updates; never equate raw JSON payloads with MongoDB update documents.

## 12. Updating Nested Fields with MongoDB Java Sync Driver

In the Java Sync Driver, use **Updates.set(...)** with dot-notation paths just like **$set** in mongosh.

Complete example:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.bson.conversions.Bson;

public class UpdateNestedFieldExample {

    public static void main(String[] args) {
        try (MongoClient client =
                     MongoClients.create("mongodb://localhost:27017")) {

            MongoDatabase database =
                    client.getDatabase("nested_update_lab");

            MongoCollection<Document> users =
                    database.getCollection("users");

            Bson filter = Filters.eq("_id", "U-1001");

            Bson update = Updates.combine(
                    Updates.set(
                            "profile.address.city",
                            "Da Nang"
                    ),
                    Updates.set(
                            "profile.preferences.language",
                            "vi"
                    ),
                    Updates.currentDate("audit.updatedAt"),
                    Updates.inc("audit.version", 1)
            );

            UpdateResult result = users.updateOne(filter, update);

            System.out.println(
                    "Matched: " + result.getMatchedCount()
            );
            System.out.println(
                    "Modified: " + result.getModifiedCount()
            );

            Document updated = users.find(filter).first();
            System.out.println(updated);
        }
    }
}
~~~

**Updates.set("profile.address.city", "Da Nang")** sets only **city**. Replacing it with:

~~~java
Updates.set(
    "profile.address",
    new Document("city", "Da Nang")
)
~~~

instructs MongoDB to **replace the entire address object** with a new document containing only **city**. The Java driver does not convert this into a deep merge.

### 12.1. Conditional Updates Using version

If multiple services edit the same user, consider optimistic version checking:

~~~java
Bson filter = Filters.and(
        Filters.eq("_id", "U-1001"),
        Filters.eq("audit.version", 3)
);

Bson update = Updates.combine(
        Updates.set("profile.address.city", "Hue"),
        Updates.inc("audit.version", 1)
);

UpdateResult result = users.updateOne(filter, update);

if (result.getMatchedCount() == 0) {
    throw new IllegalStateException(
            "Document does not exist or version has changed"
    );
}
~~~

If another writer already incremented **audit.version** to 4, the conditional update expecting version 3 matches nothing and avoids overwriting the newer change. This pattern is reliable only when every relevant write path maintains the version-increment rule.

### 12.2. Using Updates.unset for Child Fields

~~~java
users.updateOne(
    Filters.eq("_id", "U-1001"),
    Updates.unset("profile.address.postalCode")
);
~~~

This removes **postalCode** without deleting the **address** object or converting **postalCode** to null.

### 12.3. Updating Array Elements with ArrayFilters

The Java Driver supports **UpdateOptions.arrayFilters** to target specific elements:

~~~java
import com.mongodb.client.model.UpdateOptions;
import java.util.List;

// users is an already-created MongoCollection<Document>.

UpdateOptions options = new UpdateOptions()
        .arrayFilters(
                List.of(new Document("contact.type", "work"))
        );

users.updateOne(
        Filters.eq("_id", "U-1001"),
        Updates.set(
                "contacts.$[contact].phone",
                "0911111111"
        ),
        options
);
~~~

This updates **phone** on matching contact elements while leaving all other fields of those elements untouched.

## 13. Spring Data MongoDB: Distinguishing update from save

With Spring Data MongoDB, you can use **MongoTemplate** and **Update.set** to update a nested path:

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

// mongoTemplate is injected/preconfigured.

Query query = new Query(
        Criteria.where("_id").is("U-1001")
);

Update update = new Update()
        .set("profile.address.city", "Da Nang")
        .currentDate("audit.updatedAt");

mongoTemplate.updateFirst(query, update, "users");
~~~

**Update.set("profile.address.city", ...)** expresses a leaf-field patch. When a DTO only contains `city`, this is generally far safer than instantiating an entity missing other fields and calling **save** without knowing which write command the library will issue.

Some Spring Data codebases use:

~~~java
repository.save(userEntity);
~~~

This persists the **entity** according to repository semantics and current mappings. When an object holds partial data, `save` can drop unloaded fields or overwrite them with null. Additionally, entities with **@Version** follow specific optimistic-locking rules. Before using **save** to update a nested field, understand how entities are loaded and mapped and inspect the actual write command issued by the framework.

### 13.1. DTO Classes Should Express Clear Intent

Example DTO dedicated to changing the city:

~~~java
public record UpdateCityRequest(String city) {
}
~~~

The backend validates the input and builds:

~~~java
Update update = new Update()
        .set("profile.address.city", request.city());
~~~

This is clearer than accepting an entire **Profile** DTO carrying only **address.city**. APIs should define whether an omitted field means "leave unchanged" or "remove field", and never let a mapper silently replace a whole parent object.

## 14. Concurrent Updates: Avoiding Field Loss Still Does Not Prevent Lost Updates

Using dot notation prevents accidentally wiping sibling fields. However, it **does not automatically prevent all concurrent update conflicts**.

Suppose two requests both read:

~~~javascript
{
  profile: {
    address: {
      city: "Hanoi",
      district: "Ba Dinh"
    }
  }
}
~~~

Request A changes **city** to **Da Nang** using:

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  { $set: { "profile.address.city": "Da Nang" } }
);
~~~

Request B changes **district** using:

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  { $set: { "profile.address.district": "Son Tra" } }
);
~~~

Because the two commands target **two distinct leaf fields**, neither overwrites the entire `address` object. This is a practical benefit when different parts of a system update independent fields.

However, if both modify **city**:

~~~javascript
// Request A
db.users.updateOne(
  { _id: "U-1001" },
  { $set: { "profile.address.city": "Da Nang" } }
);

// Request B
db.users.updateOne(
  { _id: "U-1001" },
  { $set: { "profile.address.city": "Hue" } }
);
~~~

each write is atomic, and the final value depends on execution order. If the system must detect updates built on stale reads, add a guard on the current value or **version**.

### 14.1. Compare-and-Set Using the Expected Value

~~~javascript
const result = db.users.updateOne(
  {
    _id: "U-1001",
    "profile.address.city": "Hanoi"
  },
  {
    $set: {
      "profile.address.city": "Da Nang"
    }
  }
);

if (result.matchedCount === 0) {
  print("Value changed, or user does not exist");
}
~~~

The **city = "Hanoi"** condition is part of the update operation. If the document moved to another value before the command ran, it will not match and will not overwrite.

### 14.2. Optimistic Locking with version

~~~javascript
const result = db.users.updateOne(
  {
    _id: "U-1001",
    "audit.version": 1
  },
  {
    $set: {
      "profile.address.city": "Da Nang"
    },
    $inc: {
      "audit.version": 1
    }
  }
);
~~~

If the document exists with **version = 1**, the update changes city and increments version in a single write. If version has changed, **matchedCount = 0**. The application can then reload data, resolve the conflict, or prompt the user.

Note: the version number in the example assumes the document starts at version 1; prior exercises may have incremented it. In real usage, pass the version you just read.

### 14.3. One Write Updating Multiple Fields Is Atomic

If an application must update city and postalCode as a pair:

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: {
      "profile.address.city": "Da Nang",
      "profile.address.postalCode": "550000"
    }
  }
);
~~~

Both changes belong to **one document**, so a single-document update applies atomically. Splitting them into two commands allows another client to observe an intermediate state between writes.

## 15. MatchedCount, ModifiedCount, and Write Errors

After **updateOne**, distinguish these outcomes:

| Value | Meaning | Interpretation |
| --- | --- | --- |
| **matchedCount = 0** | No document matched the filter | Missing ID, or version/path condition no longer satisfied |
| **matchedCount = 1; modifiedCount = 1** | One document matched and actually changed | Update modified the document |
| **matchedCount = 1; modifiedCount = 0** | Document matched without content changes | E.g., setting the same existing value, or a no-op update |
| **Exception / write error** | Request failed | Possibly invalid path structure, validation failure, conflict, permissions, or server error |

Example:

~~~javascript
const result = db.users.updateOne(
  { _id: "U-1001" },
  { $set: { "profile.address.city": "Da Nang" } }
);

print("matched =", result.matchedCount);
print("modified =", result.modifiedCount);
~~~

Never assume **modifiedCount = 0** always indicates failure. The field may already hold the target value, meaning the document matched and needed no change.

Conversely, never ignore exceptions. If **profile.address** is null and code tries to traverse deeper, or one update assigns both parent and child, the operation will throw an error. Classify and handle write errors properly; never "fix" them by overwriting the entire parent object and discarding data.

## 16. Guide to Choosing Update Paths

Before writing an update, trace from business goal to path scope.

| Need | Example path or operator | Impact |
| --- | --- | --- |
| Update city | $set: { "profile.address.city": ... } | Only city |
| Update postalCode | $set: { "profile.address.postalCode": ... } | Only postalCode |
| Remove postalCode | $unset: { "profile.address.postalCode": "" } | Drops one field |
| Toggle notification flag | $set: { "profile.preferences.emailNotifications": false } | Only one flag |
| Increment version | $inc: { "audit.version": 1 } | Increments number in document |
| Update phone of work contact | contacts.$[c].phone + arrayFilters | Phone field of matching elements |
| Set all verified flags to false | contacts.$[].verified | Verified field of every element |
| Replace entire address | $set: { "profile.address": fullAddress } | All fields inside address are replaced |
| Replace entire user | replaceOne with full document | Entire document content is replaced |

Before sending to MongoDB, verify **whether it is a partial patch or a full replacement**. A "change city" request should never reassign **address**. A "replace full address" request may reassign `address`, provided it includes all fields required by the data contract.

### Common Mistakes

**Mistake 1: Using $set with a parent object for a partial patch.**  
Child fields omitted from the new object are lost. Target the specific leaf path.

**Mistake 2: Assuming $set deep-merges all levels.**  
$set assigns a value at the path; even $mergeObjects merges only one level of fields.

**Mistake 3: Using replaceOne when changing only a single value.**  
An incomplete replacement document wipes out all omitted fields.

**Mistake 4: Treating null as equivalent to an absent field.**  
$set null keeps the field; $unset removes the field.

**Mistake 5: Using fixed array indices when element order can change.**  
Use the positional operator or arrayFilters with stable identifying criteria.

**Mistake 6: Failing to handle null or wrong-type parents.**  
Dot notation cannot traverse scalar/null values; validate schema and data.

**Mistake 7: Building update paths directly from client input.**  
Risks mutating unauthorized fields; use an allowlist and validate inputs.

**Mistake 8: Assuming every HTTP PATCH is a deep merge.**  
HTTP PATCH semantics must be explicit; mappers and drivers do not guess business intent.

**Mistake 9: Ignoring matchedCount and concurrent conflicts.**  
The command may fail to match due to a changed version or missing document.

**Mistake 10: Modifying both parent and child in the same update.**  
Overlapping paths cause errors; pick one consistent update scope.

## 17. Step-by-Step Practice Lab

These exercises assume document **U-1001** from section 2 exists. If prior examples altered its structure, recreate the sample document in your test environment before comparing results.

### Exercise 1: Change Only city

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: {
      "profile.address.city": "Hai Phong"
    }
  }
);

db.users.findOne(
  { _id: "U-1001" },
  { _id: 0, "profile.address": 1 }
);
~~~

Verify in the data:

1. **city** holds the new value.
2. **district** and **postalCode** still exist.
3. **geo.lat** and **geo.lon** were not modified.
4. **profile.displayName** and **profile.preferences** were also preserved.

### Exercise 2: Observing an Accidental Object Replacement

Use a separate test document to avoid altering the sample user:

~~~javascript
db.users.insertOne({
  _id: "U-TEMP",
  profile: {
    address: {
      city: "Hanoi",
      district: "Ba Dinh",
      postalCode: "100000"
    },
    preferences: {
      language: "vi"
    }
  }
});

db.users.updateOne(
  { _id: "U-TEMP" },
  {
    $set: {
      "profile.address": {
        city: "Da Nang"
      }
    }
  }
);

db.users.findOne({ _id: "U-TEMP" });
~~~

After the update, **district** and **postalCode** are gone from `address`; **profile.preferences** remains. Explain why the assigned path level determines which fields are lost.

Re-run with **$set: { profile: { address: { city: "Hue" } } }** on a freshly initialized sample to observe the broader replacement scope.

### Exercise 3: Removing a Child Field Without Removing the Parent Object

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  {
    $unset: {
      "profile.address.postalCode": ""
    }
  }
);

db.users.findOne(
  { _id: "U-1001" },
  { _id: 0, "profile.address": 1 }
);
~~~

Compare the outcome with **$set postalCode: null**. When should an application represent "not provided by user" as a missing field versus storing explicit null?

### Exercise 4: Updating an Array Element

~~~javascript
db.users.updateOne(
  { _id: "U-1001" },
  {
    $set: {
      "contacts.$[c].verified": true
    }
  },
  {
    arrayFilters: [
      { "c.type": "work" }
    ]
  }
);

db.users.findOne(
  { _id: "U-1001" },
  { _id: 0, contacts: 1 }
);
~~~

Verify that only contacts with **type = "work"** receive **verified = true**, while phone numbers and other fields stay unchanged.

### Exercise 5: Version-Conditioned Update

~~~javascript
const before = db.users.findOne({ _id: "U-1001" });
const currentVersion = before.audit.version;

const result = db.users.updateOne(
  {
    _id: "U-1001",
    "audit.version": currentVersion
  },
  {
    $set: {
      "profile.address.city": "Hue"
    },
    $inc: {
      "audit.version": 1
    }
  }
);

printjson(result);
~~~

Re-run **the same update filter with the old currentVersion** and observe **matchedCount = 0**. Explain how `version` prevents a request built from stale data from overwriting a newer change.

### Exercise 6: Choosing Between Patch and Replace

An API receives the request:

~~~json
{
  "shippingAddress": {
    "city": "Da Nang"
  }
}
~~~

Current order document:

~~~javascript
{
  _id: "ORD-1001",
  shippingAddress: {
    recipient: "Nguyễn An",
    city: "Hanoi",
    street: "12 Pho Hue",
    instructions: "Call before delivery"
  },
  status: "CONFIRMED"
}
~~~

Write:

1. A command updating only **shippingAddress.city**, keeping **recipient**, **street**, and **instructions**.
2. A command removing only **shippingAddress.instructions**.
3. A command replacing **the entire shippingAddress** when business rules require a full replacement.
4. An additional condition forbidding address changes when **status = "DELIVERED"**.
5. A strategy to detect conflicts when two staff members update the address concurrently.

One approach for questions 1 and 4:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-1001",
    status: { $ne: "DELIVERED" }
  },
  {
    $set: {
      "shippingAddress.city": "Da Nang"
    }
  }
);
~~~

In this example, **$ne** illustrates only the status filter condition and does not replace full authorization and business rule validation.

## 18. Key Principles to Remember

When modifying a deeply nested field in MongoDB, identify the **narrowest path that needs to change**. A command:

~~~javascript
{ $set: { "parent.child.leaf": newValue } }
~~~

sets only the **leaf** field, whereas:

~~~javascript
{ $set: { "parent.child": { leaf: newValue } } }
~~~

replaces **the entire value of child**. Prior fields under `child` absent from the new object will be lost.

When the path crosses an array, select elements using **$**, **$[]**, or **$[identifier]** as appropriate. When multiple writers edit concurrently, combine guards on current values or **version** to avoid unintended overwrites. In Java and API layers, build updates from an **allowlist of leaf fields** rather than forwarding an incomplete parent object directly.

Using dot notation accurately preserves unrelated data and clarifies update scope, while schema checks, update permissions, and concurrency guards ensure the operation satisfies business requirements.

## References

- [MongoDB Manual — $set](https://www.mongodb.com/docs/manual/reference/operator/update/set/)
- [MongoDB Manual — $unset](https://www.mongodb.com/docs/manual/reference/operator/update/unset/)
- [MongoDB Manual — Dot Notation](https://www.mongodb.com/docs/manual/core/document/)
- [MongoDB Manual — Update Documents](https://www.mongodb.com/docs/manual/tutorial/update-documents/)
- [MongoDB Manual — Array Update Operators](https://www.mongodb.com/docs/manual/reference/operator/update/positional-filtered/)
- [MongoDB Manual — Updates with Aggregation Pipeline](https://www.mongodb.com/docs/manual/tutorial/update-documents-with-aggregation-pipeline/)
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
