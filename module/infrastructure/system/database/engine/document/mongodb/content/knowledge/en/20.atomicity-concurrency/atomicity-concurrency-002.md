# Preventing Lost Updates with Atomic Operators Instead of Read-Then-Write in MongoDB

In a multi-user system, two requests can read **the same document state**, compute a new value independently, and write back almost simultaneously. If both overwrite using values computed from stale data, one change can disappear. This is the **lost update** scenario.

MongoDB provides **atomic update operators** such as **$inc**, **$set**, **$min**, **$max**, **$addToSet**, **$pull**, along with the ability to attach **conditions to the update filter**. As a result, many business rules can be expressed as **a single direct write operation on the server**, instead of a sequence of read → modify in application memory → write back.

Guiding principle:

> **If a value can be transformed using an update operator on the current document, perform the transformation on the server within the same write command. Do not read the old value into the application just to compute and $set the result back.**

However, **atomicity does not mean every business conflict is automatically resolved**. Two $set commands targeting the same field can still overwrite each other depending on execution order. Updates that need to compare old state, preserve business invariants, or modify multiple documents must additionally use **conditional updates, optimistic concurrency control**, or an appropriate transaction.

This lesson explains the mechanics, mongosh and Java Sync Driver examples, contention scenarios, and how to design safe write operations in MongoDB.

## 1. How does a lost update occur?

Suppose a document stores total views:

~~~javascript
{
  _id: "ARTICLE-01",
  views: 100
}
~~~

Two requests A and B both want to increment views by one.

~~~text
A reads views = 100
B reads views = 100

A computes 100 + 1 = 101
B computes 100 + 1 = 101

A writes views = 101
B writes views = 101

Final result: 101
Expected result: 102
~~~

Each individual write can succeed. The problem is that **the assigned value came from a stale read** and does not reflect changes that just occurred.

### 1.1. Error-prone pattern causing lost updates

~~~javascript
const article = db.articles.findOne({
  _id: "ARTICLE-01"
});

const newViews = article.views + 1;

db.articles.updateOne(
  { _id: "ARTICLE-01" },
  {
    $set: {
      views: newViews
    }
  }
);
~~~

This snippet may work fine when only a single request writes. Under concurrency, **findOne** and **updateOne** are two separate operations. Between them, another writer may have incremented views.

**$set itself is still executed atomically on the document**. The lost update is the consequence of the application sending a value computed from outdated data.

### 1.2. The right way with $inc

~~~javascript
db.articles.updateOne(
  { _id: "ARTICLE-01" },
  {
    $inc: {
      views: 1
    }
  }
);
~~~

Each writer asks the server to **increment the current value by one**.

~~~text
Initial: views = 100

A: $inc views +1  -> views = 101
B: $inc views +1  -> views = 102

Final: views = 102
~~~

Neither request has to read the old number, compute 101 itself, and try to assign it back.

## 2. What does atomicity in MongoDB guarantee?

A write on **a single document** is applied atomically. If an update operation modifies multiple fields of the same document, those changes are executed as a single unit.

~~~javascript
db.accounts.updateOne(
  { _id: "ACC-01" },
  {
    $inc: {
      balanceCents: -1500,
      purchaseCount: 1
    },
    $currentDate: {
      updatedAt: true
    }
  }
);
~~~

This is **one write operation** on the account document, not three independent writes.

| Scenario | Atomicity scope |
| --- | --- |
| **updateOne** modifying one document | Single document |
| **findOneAndUpdate** | Finds and modifies one document in that operation |
| **updateMany** | Each document is atomic; the whole set is not all-or-nothing by default |
| **bulkWrite** with multiple operations | Not automatically a transaction for the group |
| Two **updateOne** calls on two documents | Not atomic together by default |
| Multi-document transaction | Can group multiple writes into one transaction when used properly |

**A single API call is not automatically a multi-document transaction.** If updateMany modifies some documents and then hits an error, the application may have to handle a partially completed state.

### 2.1. Atomicity does not prevent last-write-wins

~~~javascript
// Request A:
db.users.updateOne(
  { _id: "U-01" },
  { $set: { nickname: "An" } }
);

// Request B:
db.users.updateOne(
  { _id: "U-01" },
  { $set: { nickname: "Binh" } }
);
~~~

Each update is atomic. Yet the final nickname depends on the order in which the writes are applied. If business logic needs to detect that another writer modified the data, use **CAS or version**.

### 2.2. Update leaf fields instead of replacing the entire object

~~~javascript
db.users.updateOne(
  { _id: "U-01" },
  { $set: { "profile.city": "Hue" } }
);

db.users.updateOne(
  { _id: "U-01" },
  { $set: { "profile.language": "en" } }
);
~~~

These two commands assign two independent leaf fields. By contrast:

~~~javascript
db.users.updateOne(
  { _id: "U-01" },
  {
    $set: {
      profile: {
        language: "en"
      }
    }
  }
);
~~~

reassigns the entire profile object, which can wipe out city that another writer updated. **The update path must match the exact field level being modified.**

## 3. Creating the practice dataset

Use the test database **atomic_concurrency_lab**. Only run drop commands in a learning environment because they remove collections.

~~~javascript
use atomic_concurrency_lab

db.counters.drop();
db.products.drop();
db.orders.drop();
db.accounts.drop();
db.users.drop();

db.counters.insertOne({
  _id: "PAGE-01",
  views: NumberLong(100),
  likes: NumberLong(20),
  version: NumberLong(1)
});

db.products.insertMany([
  {
    _id: "SKU-BOOK-01",
    name: "MongoDB Book",
    available: 10,
    reserved: 0,
    version: 1
  },
  {
    _id: "SKU-PEN-02",
    name: "Pen",
    available: 3,
    reserved: 0,
    version: 1
  }
]);

db.orders.insertOne({
  _id: "ORD-1001",
  status: "PENDING",
  totalCents: NumberLong(150000),
  paymentAttempts: 0,
  tags: ["new"],
  events: [],
  version: 1
});

db.accounts.insertMany([
  {
    _id: "ACC-A",
    balanceCents: NumberLong(100000),
    version: 1
  },
  {
    _id: "ACC-B",
    balanceCents: NumberLong(50000),
    version: 1
  }
]);

db.users.insertOne({
  _id: "U-01",
  profile: {
    city: "Hanoi",
    language: "vi"
  },
  favoriteCategories: ["books"],
  version: 1
});
~~~

The account examples store **balanceCents** as an integer in an assumed smallest currency unit. For real monetary systems, choose the exact unit and data type; MongoDB also supports Decimal128 if the domain requires decimal precision.

## 4. $inc: server-side increment or decrement

**$inc** is the most important operator for avoiding lost updates on counters.

~~~javascript
db.counters.updateOne(
  { _id: "PAGE-01" },
  {
    $inc: {
      views: NumberLong(1)
    }
  }
);
~~~

Decrement likes:

~~~javascript
db.counters.updateOne(
  { _id: "PAGE-01" },
  {
    $inc: {
      likes: NumberLong(-1)
    }
  }
);
~~~

Increment views and likes together:

~~~javascript
db.counters.updateOne(
  { _id: "PAGE-01" },
  {
    $inc: {
      views: NumberLong(1),
      likes: NumberLong(1)
    }
  }
);
~~~

### 4.1. Why does $inc prevent lost updates?

| Approach | Value sent by request | Risk of lost update |
| --- | --- | --- |
| Read count = 10 then $set count = 11 | Absolute value 11 | Two requests both reading 10 can both write 11 |
| **$inc count +1** | Delta +1 | Both valid writes contribute one increment |
| **$inc count -2** | Delta -2 | Atomic subtraction, but must check against threshold |

### 4.2. When a field is missing or null

If the field does not yet exist, $inc creates the field with the delta value:

~~~javascript
db.counters.updateOne(
  { _id: "PAGE-01" },
  { $inc: { downloads: 1 } }
);
~~~

If the field holds **null** or a type incompatible with addition, $inc returns an error. Do not assume null is equivalent to 0; use schema validation, migrations, or intentional conversion.

### 4.3. Atomic increment does not bound values automatically

~~~javascript
db.products.updateOne(
  { _id: "SKU-PEN-02" },
  { $inc: { available: -5 } }
);
~~~

If available starts at 3, subtracting 5 produces available = -2. Atomicity does not automatically enforce **non-negative inventory**.

To preserve a business invariant, put the required check into the filter of **the same update**.

## 5. Conditional update: condition and change in one command

Requirement: reserve 2 items only when available ≥ 2:

~~~javascript
const quantity = 2;

const result = db.products.updateOne(
  {
    _id: "SKU-PEN-02",
    available: { $gte: quantity }
  },
  {
    $inc: {
      available: -quantity,
      reserved: quantity
    }
  }
);

printjson(result);
~~~

The condition **available ≥ quantity** is evaluated when MongoDB applies the write operation. If another writer has already decremented inventory, the filter no longer matches.

### 5.1. Two requests competing for the last items

~~~text
Initial: available = 3
A wants 2 items
B wants 2 items

A:
  condition available >= 2 is true
  subtract 2 -> available = 1
  matchedCount = 1

B:
  condition available >= 2 is false
  no write
  matchedCount = 0

Cannot oversell beyond 3 items.
~~~

With the client-read-then-overwrite model:

~~~text
A reads 3 -> sees enough
B reads 3 -> sees enough
A writes available = 1
B writes available = 1

Both requests may believe they reserved 2,
while the available field only dropped to 1.
~~~

### 5.2. Interpreting matchedCount properly

~~~javascript
if (result.matchedCount === 1) {
  print("Reservation succeeded");
} else {
  print("Product does not exist or insufficient stock");
}
~~~

**matchedCount = 0** can occur either because no matching ID exists **or** available is insufficient. The application can re-read to display a specific message, but must never use that read as the basis for an unconditional subtraction.

### 5.3. Combining status with inventory

~~~javascript
db.products.updateOne(
  {
    _id: "SKU-BOOK-01",
    status: "ACTIVE",
    available: { $gte: 2 }
  },
  {
    $inc: { available: -2 }
  }
);
~~~

The sample data does not have status yet; add status = ACTIVE first if you want this command to match. This example illustrates that **every critical business condition** can be placed into the same operation's filter.

### 5.4. Updating multiple dependent fields in one write

~~~javascript
db.products.updateOne(
  {
    _id: "SKU-BOOK-01",
    available: { $gte: 2 }
  },
  {
    $inc: {
      available: -2,
      reserved: 2,
      version: 1
    },
    $currentDate: {
      updatedAt: true
    }
  }
);
~~~

Decrementing available, incrementing reserved, incrementing version, and updating the timestamp belong to one atomic operation on the product document.

If split apart:

~~~javascript
db.products.updateOne(
  { _id: "SKU-BOOK-01" },
  { $inc: { available: -2 } }
);

db.products.updateOne(
  { _id: "SKU-BOOK-01" },
  { $inc: { reserved: 2 } }
);
~~~

the process could stop between the two writes, or another writer could read an intermediate state. If fields belong to the same single-document invariant, combine them in one update.

## 6. $min and $max: do not read and compare manually

Some updates only need to retain the lowest or highest value ever observed.

Suppose we have:

~~~javascript
{
  _id: "SKU-01",
  bestPriceCents: 100000,
  maxObservedScore: 82
}
~~~

Risky pattern:

~~~javascript
const product = db.products.findOne({
  _id: "SKU-01"
});

if (90000 < product.bestPriceCents) {
  db.products.updateOne(
    { _id: "SKU-01" },
    {
      $set: {
        bestPriceCents: 90000
      }
    }
  );
}
~~~

While the request reads 100000 and prepares to write 90000, another writer may have already set bestPriceCents = 85000. The slower request then overwrites with 90000 and **loses the better price**.

Use **$min**:

~~~javascript
db.products.updateOne(
  { _id: "SKU-01" },
  {
    $min: {
      bestPriceCents: 90000
    }
  }
);
~~~

Use **$max** for the highest score:

~~~javascript
db.products.updateOne(
  { _id: "SKU-01" },
  {
    $max: {
      maxObservedScore: 95
    }
  }
);
~~~

### 6.1. Transformation operators

| Operator | Rule | Example |
| --- | --- | --- |
| **$inc** | Adds delta | Views, quantities |
| **$min** | Keeps the smaller value | Lowest price seen |
| **$max** | Keeps the larger value | Highest score, watermark |
| **$mul** | Multiplies the current value | Growth factor in certain domains |
| **$currentDate** | Sets current date/timestamp as configured | updatedAt |

$min/$max rely on BSON comparison rules, so keep field types consistent. Avoid using them accidentally on a field that is sometimes a string and sometimes a number.

### 6.2. Atomic does not mean idempotent

~~~javascript
db.products.updateOne(
  { _id: "SKU-01" },
  {
    $mul: {
      multiplier: 2
    }
  }
);
~~~

If the same request is applied twice, multiplier is multiplied twice. $mul is an atomic transformation, yet it does not protect against business-level retries.

## 7. $set with a state filter: safe state transitions

**$set** is suitable for assigning a target state. When a transition is only allowed from a specific prior state, put that prior state in the filter.

~~~javascript
const result = db.orders.updateOne(
  {
    _id: "ORD-1001",
    status: "PENDING"
  },
  {
    $set: {
      status: "PAID"
    },
    $currentDate: {
      paidAt: true
    },
    $inc: {
      version: 1
    }
  }
);

printjson(result);
~~~

If another writer has already changed status to CANCELLED, the status PENDING filter will not match, so this request will not overwrite CANCELLED with PAID.

### 7.1. Two competing transitions

~~~text
PENDING
  |       |
  v       v
PAID   CANCELLED
~~~

Two requests sent:

~~~javascript
// Pay:
db.orders.updateOne(
  {
    _id: "ORD-1001",
    status: "PENDING"
  },
  {
    $set: {
      status: "PAID"
    }
  }
);
~~~

~~~javascript
// Cancel:
db.orders.updateOne(
  {
    _id: "ORD-1001",
    status: "PENDING"
  },
  {
    $set: {
      status: "CANCELLED"
    }
  }
);
~~~

Once one operation transitions status out of PENDING, the other no longer matches. This protects the rule that **an order may only transition out of PENDING once**.

### 7.2. Atomic transition does not cover emails and external APIs

Success of status = PAID does not mean the following steps were also executed atomically:

- Sending a confirmation email.
- Creating an invoice in another collection.
- Calling a payment system.
- Publishing a message to a broker.
- Decrementing inventory in another document.

If those steps must be consistent, you must design transactions, outbox, idempotency, or an appropriate recovery process.

## 8. Compare-and-set (CAS) by prior value

When a user edits a form from previously read data, **CAS** can write only if the field still holds the prior value.

Suppose the user read city = Hanoi, then wants to change it to Hue:

~~~javascript
const result = db.users.updateOne(
  {
    _id: "U-01",
    "profile.city": "Hanoi"
  },
  {
    $set: {
      "profile.city": "Hue"
    }
  }
);

if (result.matchedCount === 0) {
  print("Document does not exist or city has changed");
}
~~~

If another writer changed city to Da Nang, the operation with condition city = Hanoi will not match and will not overwrite.

### 8.1. When is field-level CAS appropriate?

- Only one field needs conflict control.
- The input is a new value based on the old value the client saw.
- Other fields can be updated independently by other writers.

### 8.2. The ABA limitation

~~~text
A reads city = Hanoi

B changes city: Hanoi -> Da Nang
C changes city: Da Nang -> Hanoi

A writes with CAS city = Hanoi
-> matches again
~~~

CAS only inspects the current value; it does not detect a history of changing away and returning to the old value. When you need to detect **any change at all** since the read, use a **version** field.

## 9. Optimistic concurrency control using version

Document includes version:

~~~javascript
{
  _id: "U-01",
  profile: {
    city: "Hanoi",
    language: "vi"
  },
  version: 1
}
~~~

Client reads version = 1. When writing:

~~~javascript
const expectedVersion = 1;

const result = db.users.updateOne(
  {
    _id: "U-01",
    version: expectedVersion
  },
  {
    $set: {
      "profile.city": "Hue"
    },
    $inc: {
      version: 1
    }
  }
);

if (result.matchedCount === 0) {
  print("Does not exist or version has changed");
}
~~~

### 9.1. Two requests reading the same version

~~~text
Initial: version = 1

A reads version 1, wants city = Hue
B reads version 1, wants language = en

A:
  filter version 1 -> matches
  set city, inc version -> version 2

B:
  filter version 1 -> does not match
  matchedCount = 0
~~~

B must handle the conflict. If the two fields are completely independent, a shared version causing extra conflicts is an **intentional trade-off** to ensure the document is managed as a unit.

### 9.2. Rules for reliable versioning

1. On read, return the current version.
2. On write, use the read version as a filter condition.
3. Increment version in **the same** update.
4. Check matchedCount after the update.
5. On conflict, re-read and handle according to business rules.

If a writer modifies the document **without incrementing version**, the version mechanism no longer detects all changes. Services, maintenance scripts, and update repositories must follow the same convention.

### 9.3. Do not handle conflicts by dropping the condition

Wrong:

~~~text
Update with version fails
-> drop version filter
-> use $set with stale data to force success
~~~

Doing so renders conflict detection meaningless.

Depending on the system, you can return **HTTP 409 Conflict**, display the newer changes for the user to merge, or perform bounded retries after recomputing on the current state if the calculation genuinely allows it.

## 10. Do not replace the whole document just to edit one field

A severe form of lost update occurs when the application loads the whole document into a DTO, modifies one field, and calls replaceOne:

~~~javascript
const order = db.orders.findOne({
  _id: "ORD-1001"
});

// Suppose another writer just appended events.
order.status = "PAID";

db.orders.replaceOne(
  { _id: "ORD-1001" },
  order
);
~~~

If the loaded order data is an old snapshot, replacement can overwrite **events**, **paymentAttempts**, or other recently changed fields.

Comparison:

| Approach | Scope | Additional guarantee |
| --- | --- | --- |
| **replaceOne** with read document | Replaces entire document | Easily overwrites unintended data |
| **$set { status: "PAID" }** | Only status field | Preserves other fields, though status can still be last-write-wins |
| **$set status with filter status: PENDING** | Single field, conditional | Protects state transition |
| **$set status with version filter and $inc version** | Version-conditional | Detects whether the document was modified |

### 10.1. Dot notation avoids replacing an entire subdocument

~~~javascript
db.users.updateOne(
  { _id: "U-01" },
  {
    $set: {
      "profile.city": "Hue"
    }
  }
);
~~~

Do not assign the entire **profile** when changing only city:

~~~javascript
db.users.updateOne(
  { _id: "U-01" },
  {
    $set: {
      profile: {
        city: "Hue"
      }
    }
  }
);
~~~

The second command wipes out profile.language because it **replaces the whole profile object**.

## 11. $addToSet and $pull: modifying arrays on the server

Suppose user has:

~~~javascript
{
  _id: "U-01",
  favoriteCategories: ["books"]
}
~~~

Read-then-reassign-array pattern:

~~~javascript
const user = db.users.findOne({
  _id: "U-01"
});

const updated = [
  ...user.favoriteCategories,
  "music"
];

db.users.updateOne(
  { _id: "U-01" },
  {
    $set: {
      favoriteCategories: updated
    }
  }
);
~~~

If another writer just added **sports** to the array, the updated array built from the stale snapshot can overwrite and lose sports.

### 11.1. Use $addToSet

~~~javascript
db.users.updateOne(
  { _id: "U-01" },
  {
    $addToSet: {
      favoriteCategories: "music"
    }
  }
);
~~~

Another request:

~~~javascript
db.users.updateOne(
  { _id: "U-01" },
  {
    $addToSet: {
      favoriteCategories: "sports"
    }
  }
);
~~~

Each command mutates the array on the server without resending the entire old array.

### 11.2. Adding multiple elements with $each

~~~javascript
db.users.updateOne(
  { _id: "U-01" },
  {
    $addToSet: {
      favoriteCategories: {
        $each: ["music", "sports"]
      }
    }
  }
);
~~~

### 11.3. Removing elements with $pull

~~~javascript
db.users.updateOne(
  { _id: "U-01" },
  {
    $pull: {
      favoriteCategories: "books"
    }
  }
);
~~~

If another writer is adding an element concurrently, $pull does not reassign the entire array, reducing the risk of losing newly added elements compared to reading and writing the whole array.

### 11.4. $push can still create duplicates on retry

~~~javascript
db.orders.updateOne(
  { _id: "ORD-1001" },
  {
    $push: {
      events: {
        type: "PAYMENT_ATTEMPTED",
        at: new Date()
      }
    }
  }
);
~~~

If the command is **applied twice**, the array gets two events. That is right for two distinct payment attempts, but wrong if the second call is only a retry of the same business request.

| Operator | Semantics |
| --- | --- |
| **$addToSet** | Adds a value if not already present per MongoDB comparison rules |
| **$push** | Appends an element, duplicates allowed |
| **$pull** | Removes elements matching a condition |
| **$pop** | Removes first or last array element per operator rules |

**$addToSet does not replace unique indexes for all business relationships** and does not deduplicate elements that already exist. For embedded documents, equality comparison also depends on structure and field order per MongoDB rules.

## 12. Atomically updating array elements

Suppose an order has:

~~~javascript
{
  _id: "ORD-2001",
  items: [
    {
      sku: "BOOK-01",
      quantity: 1,
      fulfilled: false
    },
    {
      sku: "PEN-02",
      quantity: 2,
      fulfilled: false
    }
  ]
}
~~~

Increment quantity of BOOK-01:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-2001",
    "items.sku": "BOOK-01"
  },
  {
    $inc: {
      "items.$.quantity": 1
    }
  }
);
~~~

The positional **$** operator represents the first array element matching the query condition in supported contexts.

### 12.1. Using arrayFilters

~~~javascript
db.orders.updateOne(
  { _id: "ORD-2001" },
  {
    $inc: {
      "items.$[line].quantity": 1
    }
  },
  {
    arrayFilters: [
      { "line.sku": "BOOK-01" }
    ]
  }
);
~~~

If multiple elements satisfy the condition, the filtered positional operator modifies all matching elements. If only one line per sku is permitted, enforce that rule in the data model or business logic.

### 12.2. Do not replace an entire element to edit one field

Dangerous:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-2001" },
  {
    $set: {
      "items.0": {
        quantity: 3
      }
    }
  }
);
~~~

This replaces the whole item object at index 0, wiping out sku and fulfilled.

Instead:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-2001" },
  {
    $set: {
      "items.0.quantity": 3
    }
  }
);
~~~

However, a fixed index can shift if the array is reordered. Use a lineId or sku identifier with arrayFilters if that is the right business selector.

### 12.3. $elemMatch when conditions must apply to the same element

Do not assume that:

~~~javascript
{
  "items.sku": "BOOK-01",
  "items.quantity": { $gte: 1 }
}
~~~

requires both conditions to match the same item. They can match different elements in the array.

Use **$elemMatch** when the same element must match:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-2001",
    items: {
      $elemMatch: {
        sku: "BOOK-01",
        quantity: { $gte: 1 }
      }
    }
  },
  {
    $inc: {
      "items.$.quantity": -1
    }
  }
);
~~~

The condition and decrement are applied in one write, with the filter protecting the rule for the matching element.

## 13. Updates with an aggregation pipeline

When a transformation must be computed from **multiple current fields**, you can use an update pipeline to perform the calculation on the server.

Suppose an invoice has:

~~~javascript
{
  _id: "INV-01",
  quantity: 3,
  unitPriceCents: 12000,
  amountCents: 36000
}
~~~

Recompute amount:

~~~javascript
db.invoices.updateOne(
  { _id: "INV-01" },
  [
    {
      $set: {
        amountCents: {
          $multiply: [
            "$quantity",
            "$unitPriceCents"
          ]
        }
      }
    }
  ]
);
~~~

The calculation is evaluated against the current field values inside the update operation on the document.

### 13.1. When only incrementing a number, $inc is simpler

~~~javascript
db.counters.updateOne(
  { _id: "PAGE-01" },
  [
    {
      $set: {
        views: {
          $add: [
            { $ifNull: ["$views", 0] },
            1
          ]
        }
      }
    }
  ]
);
~~~

This pipeline expresses incrementing views on the server, but if the field is always a valid number, **$inc** is clearer and shorter.

### 13.2. Distinguishing the $set stage from the $set update operator

~~~javascript
// Update operator:
db.orders.updateOne(
  { _id: "ORD-1001" },
  {
    $set: {
      status: "PAID"
    }
  }
);
~~~

~~~javascript
// Aggregation pipeline update:
db.orders.updateOne(
  { _id: "ORD-1001" },
  [
    {
      $set: {
        status: {
          $cond: [
            { $eq: ["$status", "PENDING"] },
            "PAID",
            "$status"
          ]
        }
      }
    }
  ]
);
~~~

In a pipeline, $set is an **aggregation stage** and values can be expressions. For simple transitions, a status PENDING filter + update operator usually makes checking matchedCount easier.

### 13.3. Filters are still needed to protect invariants

~~~javascript
db.products.updateOne(
  {
    _id: "SKU-BOOK-01",
    available: { $gte: 2 }
  },
  [
    {
      $set: {
        available: {
          $subtract: ["$available", 2]
        },
        reserved: {
          $add: ["$reserved", 2]
        }
      }
    }
  ]
);
~~~

This is one way to express an atomic reservation using expressions. When the formula is simply adding/subtracting constants, using $inc for both available and reserved is usually easier to read.

## 14. findOneAndUpdate: modify and retrieve the result in one operation

Sometimes the application needs the counter or stock number **immediately after its own operation**.

Two separate commands:

~~~javascript
db.counters.updateOne(
  { _id: "PAGE-01" },
  { $inc: { views: 1 } }
);

const current = db.counters.findOne({
  _id: "PAGE-01"
});
~~~

In between them, another writer can increment views further, so current.views is not necessarily the value right after **only** the first request's increment.

Use:

~~~javascript
const updated = db.counters.findOneAndUpdate(
  { _id: "PAGE-01" },
  {
    $inc: {
      views: 1
    }
  },
  {
    returnDocument: "after"
  }
);

printjson(updated);
~~~

In mongosh, returnDocument = "after" requests returning the document after the update. This method keeps the modification and value retrieval within the same find-and-modify operation.

**Limitation:** Another writer can still update the document right after this operation completes, so the returned value is not a guarantee that state remains unchanged until the client uses it.

### 14.1. When to use updateOne or findOneAndUpdate?

- Only need to know if it matched and updated: **updateOne** is usually sufficient.
- Need the before/after document in the same operation: **findOneAndUpdate**.
- Need to modify multiple documents all-or-nothing: evaluate **transactions**, do not use findOneAndUpdate assuming it acts on the whole collection.

## 15. No shared atomicity across multiple documents

Transfer 10,000 smallest units from account A to B:

~~~javascript
db.accounts.updateOne(
  { _id: "ACC-A" },
  {
    $inc: {
      balanceCents: NumberLong(-10000)
    }
  }
);

db.accounts.updateOne(
  { _id: "ACC-B" },
  {
    $inc: {
      balanceCents: NumberLong(10000)
    }
  }
);
~~~

Each update is atomic on a single account. However, **the two updates are not atomic together**. The process could stop after debiting A without crediting B.

If both steps must commit together, use a **multi-document transaction** under supported topologies and conditions, or design a ledger, idempotency, and reconciliation according to business requirements.

### 15.1. Transaction illustration

~~~javascript
const session = db.getMongo().startSession();

try {
  const database = session.getDatabase("atomic_concurrency_lab");
  const accounts = database.getCollection("accounts");

  session.startTransaction();

  const debit = accounts.updateOne(
    {
      _id: "ACC-A",
      balanceCents: { $gte: NumberLong(10000) }
    },
    {
      $inc: {
        balanceCents: NumberLong(-10000)
      }
    }
  );

  if (debit.matchedCount !== 1) {
    throw new Error("Insufficient funds or account A not found");
  }

  const credit = accounts.updateOne(
    { _id: "ACC-B" },
    {
      $inc: {
        balanceCents: NumberLong(10000)
      }
    }
  );

  if (credit.matchedCount !== 1) {
    throw new Error("Account B not found");
  }

  session.commitTransaction();
} catch (error) {
  session.abortTransaction();
  throw error;
} finally {
  session.endSession();
}
~~~

This example demonstrates transaction scope and **does not yet** implement full retries for transient transaction errors, unknown commit results, idempotency, and financial rules. For real deployments, use the appropriate driver APIs and handle uncertain commit states.

### 15.2. When is a transaction unnecessary?

If the invariant resides in a single document, **one conditional updateOne** is usually simpler and has less overhead. Transactions are only needed when consistency requirements genuinely cross document boundaries.

## 16. Retryable writes and idempotency

Consider this scenario:

~~~text
Client sends $inc views +1
Server may have already updated views
Connection drops before client receives response
Client is uncertain of the outcome
~~~

If the application issues a new command and calls $inc +1 again, **the same view can be counted twice**.

### 16.1. Three distinct concepts

- **Atomicity:** an update on a document is applied as a single unit.
- **Idempotency:** repeating the same business request without duplicating its effect.
- **Retryable write:** a driver/server mechanism that retries the same logical write under specific conditions.

$inc and $push are **not idempotent if applied as multiple independent operations**.

### 16.2. Driver retries differ from business retries

MongoDB drivers can use a session/transaction number to recognize retries of **the same logical write** when the operation and topology support it.

However:

~~~text
Driver retrying the same logical write
~~~

differs from:

~~~text
Application catching a timeout and creating a new business request
~~~

Do not assume driver retryable writes solve all duplicate business commands across process restarts or multiple HTTP requests.

### 16.3. Idempotency marker in the same document

Suppose a job adds rewardPoints = 10 only once per jobId:

~~~javascript
const jobId = "REWARD-2026-11";

db.accounts.updateOne(
  {
    _id: "ACC-A",
    appliedRewards: { $ne: jobId }
  },
  {
    $inc: {
      rewardPoints: 10
    },
    $addToSet: {
      appliedRewards: jobId
    }
  }
);
~~~

The filter and changes are in the same atomic update. If jobId is already present, a repeat operation will not match and will not add points again.

**Limitation:** the appliedRewards array can grow unboundedly. For high request volumes, design bounded/expiring markers, a ledger, or a separate collection; when the marker and reward points live on separate documents, you must address the atomicity boundary again.

### 16.4. Avoiding duplicated side effects outside the database

Even a command like:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-1001" },
  {
    $set: {
      status: "PAID"
    }
  }
);
~~~

may be idempotent regarding final state, yet if every request completion triggers **sending an email** or **creating an invoice**, those side effects can still repeat.

Proper design may require an **outbox** or idempotency keys in downstream systems.

## 17. Upsert and duplicate insert risk under contention

Upsert combines lookup and insert/update on the server:

~~~javascript
db.counters.updateOne(
  { _id: "PAGE-NEW" },
  {
    $inc: {
      views: 1
    }
  },
  {
    upsert: true
  }
);
~~~

When the filter is based on _id, the default unique _id index prevents two documents from sharing the same _id.

However, if the filter uses fields **without a unique index**, two concurrent upserts can both determine that no document exists yet and insert **two documents with duplicate business keys**.

Example daily counter:

~~~javascript
db.dailyCounters.updateOne(
  {
    day: "2026-11-14",
    pageId: "PAGE-01"
  },
  {
    $inc: {
      views: 1
    }
  },
  {
    upsert: true
  }
);
~~~

If the pair (day, pageId) must be unique:

~~~javascript
db.dailyCounters.createIndex(
  { day: 1, pageId: 1 },
  {
    unique: true,
    name: "uq_daily_page"
  }
);
~~~

A unique index enforces the uniqueness invariant at the database level. When multiple upserts race on the same key, clients can still receive duplicate key errors; classify the error and retry according to proper rules.

### 17.1. $setOnInsert

~~~javascript
db.dailyCounters.updateOne(
  {
    day: "2026-11-14",
    pageId: "PAGE-01"
  },
  {
    $inc: {
      views: 1
    },
    $setOnInsert: {
      createdAt: new Date()
    }
  },
  {
    upsert: true
  }
);
~~~

**$setOnInsert** sets fields only when the upsert inserts a new document, without overwriting createdAt on subsequent counter increments.

## 18. Data types and schema validation

Update operators have data type requirements:

| Operator | Important notes |
| --- | --- |
| **$inc** | Field must have a compatible numeric type or not yet exist; null causes an error |
| **$mul** | Numeric multiplication; not compatible with arbitrary types |
| **$min/$max** | Uses BSON comparison, so keep field types consistent |
| **$addToSet/$push/$pull** | Operates on arrays per operator rules |
| **$set** | Replaces the value at the exact path, even if the path is a parent object |
| **$currentDate** | Sets current date/time, does not guarantee idempotency on retry |

JSON Schema validation can reduce type errors:

~~~javascript
db.createCollection("validatedCounters", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["views"],
      properties: {
        views: {
          bsonType: ["int", "long"],
          description: "views must be an integer"
        }
      }
    }
  }
});
~~~

Validators help catch schema-invalid data. However, dynamic conditions like **available ≥ quantity** still require protection via an appropriate filter/update.

## 19. Write concern and read concern do not replace atomic updates

| Mechanism | Question it addresses |
| --- | --- |
| **Atomic update** | Is a write on a document applied atomically? |
| **Conditional filter** | Does the business condition still hold at write time? |
| **Version/CAS** | Did another writer modify the data after the request read it? |
| **Write concern** | What is the acknowledgment level of the write operation? |
| **Read concern** | What is the consistency level of the read data? |
| **Transaction** | Is atomicity needed across multiple documents? |

Setting **write concern majority** does not fix the lost update pattern of reading count = 10 and then $set count = 11. It relates to acknowledgment/durability, not turning a client read + write into one atomic command.

Similarly, reading with a higher consistency level does not make a decision **computed from a prior read** valid if another writer has since modified the document.

### 19.1. Uncertain write outcome due to network issues

If a client times out after a write, the outcome can be **indeterminate from the client's perspective**. Do not assume the write did not happen. For non-idempotent operations, you need a business request identifier or appropriate reconciliation.

## 20. Java Sync Driver: Updates.inc

Java Sync Driver example:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

public class AtomicCounterExample {

    public static void main(String[] args) {
        try (MongoClient client =
                MongoClients.create("mongodb://localhost:27017")) {

            MongoDatabase db =
                    client.getDatabase("atomic_concurrency_lab");

            MongoCollection<Document> counters =
                    db.getCollection("counters");

            UpdateResult result = counters.updateOne(
                    Filters.eq("_id", "PAGE-01"),
                    Updates.inc("views", 1L)
            );

            System.out.println(
                    "Matched: " + result.getMatchedCount()
            );
            System.out.println(
                    "Modified: " + result.getModifiedCount()
            );
        }
    }
}
~~~

**Updates.inc("views", 1L)** delegates the increment to the MongoDB server without needing the client to read views first and write back a computed number.

### 20.1. Incorrect read–modify–write pattern in Java

~~~java
Document doc = counters.find(
        Filters.eq("_id", "PAGE-01")
).first();

long nextViews = doc.getLong("views") + 1L;

counters.updateOne(
        Filters.eq("_id", "PAGE-01"),
        Updates.set("views", nextViews)
);
~~~

Between find and update, another writer can increment views. **nextViews** is based on an old snapshot, so updates can be lost. The Java Driver cannot automatically know the true intent was an increment.

## 21. Java Sync Driver: conditional stock deduction

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.bson.conversions.Bson;

public class ReserveStockExample {

    public static void main(String[] args) {
        String productId = "SKU-BOOK-01";
        int quantity = 2;

        try (MongoClient client =
                MongoClients.create("mongodb://localhost:27017")) {

            MongoCollection<Document> products =
                    client.getDatabase("atomic_concurrency_lab")
                            .getCollection("products");

            Bson filter = Filters.and(
                    Filters.eq("_id", productId),
                    Filters.gte("available", quantity)
            );

            Bson update = Updates.combine(
                    Updates.inc("available", -quantity),
                    Updates.inc("reserved", quantity),
                    Updates.inc("version", 1),
                    Updates.currentDate("updatedAt")
            );

            UpdateResult result =
                    products.updateOne(filter, update);

            if (result.getMatchedCount() == 1) {
                System.out.println("Reservation succeeded");
            } else {
                System.out.println(
                        "Product does not exist or insufficient stock"
                );
            }
        }
    }
}
~~~

The condition is checked by the MongoDB server together with the update. A **synchronized** block in the JVM cannot replace this filter when the database can also be written by other processes.

## 22. Java Sync Driver: optimistic locking

~~~java
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.conversions.Bson;

// users is an initialized MongoCollection<Document>.

int expectedVersion = 1;

Bson filter = Filters.and(
        Filters.eq("_id", "U-01"),
        Filters.eq("version", expectedVersion)
);

Bson update = Updates.combine(
        Updates.set("profile.city", "Hue"),
        Updates.inc("version", 1)
);

UpdateResult result = users.updateOne(filter, update);

if (result.getMatchedCount() == 0) {
    throw new IllegalStateException(
            "Document does not exist or concurrent modification occurred"
    );
}
~~~

### 22.1. Client must carry the version it read

~~~text
GET /users/U-01
  -> returns profile and version = 7

Client edits form

PATCH /users/U-01
  -> sends new city, expectedVersion = 7

Server:
  updateOne({_id, version:7},
            {$set city, $inc version:1})
~~~

If another writer incremented version to 8, this request does not match. Do not read the **latest** version right before writing and use it to bypass conflict checking for an old form submission.

### 22.2. Not every conflict can be automatically retried

If two people edit the same address, retrying by re-applying old data after reading the new version can erase the other person's intent. You may need to surface the conflict, let the user merge, or define a business precedence rule.

## 23. Java Sync Driver: findOneAndUpdate

~~~java
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.FindOneAndUpdateOptions;
import com.mongodb.client.model.ReturnDocument;
import com.mongodb.client.model.Updates;
import org.bson.Document;

// products is an initialized MongoCollection<Document>.

int quantity = 2;

Document after = products.findOneAndUpdate(
        Filters.and(
                Filters.eq("_id", "SKU-BOOK-01"),
                Filters.gte("available", quantity)
        ),
        Updates.combine(
                Updates.inc("available", -quantity),
                Updates.inc("reserved", quantity)
        ),
        new FindOneAndUpdateOptions()
                .returnDocument(ReturnDocument.AFTER)
);

if (after == null) {
    System.out.println("Insufficient stock or product not found");
} else {
    System.out.println(
            "Remaining: " + after.getInteger("available")
    );
}
~~~

**findOneAndUpdate** returns the before/after document as configured in the same operation. Another writer can still update it after the operation finishes.

## 24. Simulating multiple writers in Node.js

To observe the difference between $inc and read–modify–write, use the **MongoDB Node.js Driver** on a test collection.

### 24.1. Incrementing 100 times with $inc

~~~javascript
import { MongoClient } from "mongodb";

const uri = process.env.MONGODB_URI
  ?? "mongodb://localhost:27017";

const client = new MongoClient(uri);

try {
  await client.connect();

  const counters = client
    .db("atomic_concurrency_lab")
    .collection("counters");

  await counters.updateOne(
    { _id: "CONCURRENT-COUNTER" },
    { $set: { views: 0 } },
    { upsert: true }
  );

  const count = 100;

  await Promise.all(
    Array.from({ length: count }, () =>
      counters.updateOne(
        { _id: "CONCURRENT-COUNTER" },
        { $inc: { views: 1 } }
      )
    )
  );

  const result = await counters.findOne({
    _id: "CONCURRENT-COUNTER"
  });

  console.log("views =", result.views);
} finally {
  await client.close();
}
~~~

If all 100 writes are applied successfully, the expected result is **views = 100**.

### 24.2. Reproducing the bug with separate read and write phases

In another script using a connected client:

~~~javascript
const counters = client
  .db("atomic_concurrency_lab")
  .collection("counters");

await counters.updateOne(
  { _id: "CONCURRENT-COUNTER" },
  { $set: { views: 0 } }
);

// Let all 100 tasks finish reading before any task writes.
const snapshots = await Promise.all(
  Array.from({ length: 100 }, () =>
    counters.findOne({ _id: "CONCURRENT-COUNTER" })
  )
);

// Each task writes the value computed from its own snapshot.
await Promise.all(
  snapshots.map(snapshot =>
    counters.updateOne(
      { _id: "CONCURRENT-COUNTER" },
      {
        $set: {
          views: snapshot.views + 1
        }
      }
    )
  )
);

console.log(
  await counters.findOne({ _id: "CONCURRENT-COUNTER" })
);
~~~

If every snapshot has views = 0, every write executes $set views = 1, so the result is **1 instead of 100**. The experiment deliberately forces reads to complete before writes to make the lost update unmistakable.

In reality requests interleave more randomly, so the symptom does not always look identical.

## 25. Hot documents and throughput limits

A shared counter:

~~~javascript
db.metrics.updateOne(
  { _id: "GLOBAL-VIEWS" },
  { $inc: { count: 1 } }
);
~~~

may be correct in atomicity yet become a **hot document** if writer volume is massive. Atomicity does not mean throughput scales infinitely as you add threads.

### 25.1. Sharded counters at the data model layer

Increments can be spread across multiple documents:

~~~text
counter-0
counter-1
counter-2
...
counter-N

Logical total = sum(count across counter documents)
~~~

Each request updates one partition, reducing contention on a single document. Reading the total requires aggregating across multiple counters, so you must evaluate acceptable latency and consistency.

### 25.2. Trade-offs

- Writes are more distributed.
- Reading totals requires extra work.
- Instantaneous exact totals are harder in distributed systems.
- Idempotency is still needed for events that can be redelivered.
- Managing partition count and load distribution adds overhead.

Do not overcomplicate a counter based solely on theoretical fears. Measure actual throughput, latency, and contention before changing the data model.

## 26. Quick decision table

| Need | Suggested mechanism | Reason |
| --- | --- | --- |
| Increment views | **$inc** | Avoids reading then setting stale value + 1 |
| Decrement stock with floor | **Filter available ≥ q + $inc -q** | Checks and updates in the same write |
| Change PENDING to PAID | **Filter status PENDING + $set PAID** | Protects transition rules |
| Add category to array | **$addToSet** | Avoids overwriting the entire array |
| Remove category from array | **$pull** | Mutates current array directly |
| Record lowest price | **$min** | Compares and stores on server |
| Record highest score | **$max** | Never overwrites with a lower score |
| Edit form from read state | **CAS/version** | Detects conflicts |
| Change multiple dependent fields in one document | **Combined single updateOne** | Document-level atomic |
| Complex formula from current fields | **Update pipeline** | Avoids client-side read–modify–write |
| Modify and retrieve new value | **findOneAndUpdate** | One find-and-modify operation |
| Transfer money between two accounts | **Transaction/ledger** | Invariant spans multiple documents |
| Send email once after write | **Outbox/idempotency** | External side effect outside database |

## 27. Common mistakes

**Mistake 1: Thinking $set is not atomic.**  
$set is atomic on the document; lost updates come from assigning a value computed from a stale read.

**Mistake 2: Using $inc without threshold checks.**  
$inc can drive stock negative. Place the condition available ≥ quantity in the same filter.

**Mistake 3: Unconditional state transitions.**  
Two requests to "pay" and "cancel" can overwrite each other. Filter on the prior state.

**Mistake 4: Using replaceOne or $set on a parent object for small patches.**  
Can erase fields someone else just updated. Use leaf field paths.

**Mistake 5: Treating matchedCount = 0 as only "ID not found."**  
It can be due to out-of-stock, changed version, or invalid state.

**Mistake 6: Having a version field while some writers forget to increment it.**  
Optimistic concurrency loses reliability.

**Mistake 7: Retrying a new $inc/$push when uncertain whether the previous write ran.**  
Can duplicate side effects. Use idempotency keys or designed retry rules.

**Mistake 8: Treating $addToSet as a universal unique index.**  
It has specific semantics for array values, not cross-document invariants.

**Mistake 9: Using synchronized inside one process to lock the database.**  
Writers from other processes can still write. Shared invariants must be protected on the server.

**Mistake 10: Treating bulkWrite/updateMany as multi-document transactions.**  
Each document is atomic, not the entire batch all-or-nothing.

**Mistake 11: Using majority write concern instead of CAS.**  
Write concern governs acknowledgment, not eliminating client read-to-write races.

**Mistake 12: Assuming update success means all side effects succeeded.**  
Emails, payments, message brokers, and writes in other collections need their own rules.

## 28. Practice exercises

The exercises assume the dataset from section 3 has been created. When comparing from initial state, re-initialize the corresponding documents in your test environment.

### Exercise 1 – Lost update timeline

Given counter count = 10, two requests both read 10, compute 11, and write 11. Draw the timeline, state the actual result, the expected result, and explain why two $inc +1 operations fix this situation.

### Exercise 2 – Atomically incrementing two counters

~~~javascript
db.counters.updateOne(
  { _id: "PAGE-01" },
  {
    $inc: {
      views: 1,
      likes: 1
    }
  }
);
~~~

Answer:

1. How many documents are modified?
2. How many write operations occur?
3. Why is there no need to read views and likes beforehand?
4. What happens if views is null instead of a number?

### Exercise 3 – Non-negative stock deduction

Product SKU-PEN-02 has available = 3. Two requests each want 2.

~~~javascript
db.products.updateOne(
  {
    _id: "SKU-PEN-02",
    available: { $gte: 2 }
  },
  {
    $inc: {
      available: -2
    }
  }
);
~~~

Run twice and observe matchedCount and available. Why can the second request not deduct further when only 1 remains?

### Exercise 4 – Conditional state transition

A PENDING order is either paid or cancelled:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-1001",
    status: "PENDING"
  },
  {
    $set: { status: "PAID" }
  }
);
~~~

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-1001",
    status: "PENDING"
  },
  {
    $set: { status: "CANCELLED" }
  }
);
~~~

What order does the final outcome depend on? Why can both not succeed in transitioning from the same PENDING state when applied sequentially to a single document?

### Exercise 5 – Editing profile with the right path

Compare:

~~~javascript
{
  $set: {
    "profile.city": "Hue"
  }
}
~~~

and:

~~~javascript
{
  $set: {
    profile: {
      city: "Hue"
    }
  }
}
~~~

Which approach drops profile.language if that field is omitted from the new object?

### Exercise 6 – Version conflict

Two requests both read version = 1. One updates city and increments version; the other tries to change language with version = 1. Write both commands and interpret matchedCount. If the two fields are independent, is there a schema design way to reduce excessive conflicts?

### Exercise 7 – Updating arrays without losing elements

~~~javascript
db.users.updateOne(
  { _id: "U-01" },
  {
    $addToSet: {
      favoriteCategories: "music"
    }
  }
);

db.users.updateOne(
  { _id: "U-01" },
  {
    $pull: {
      favoriteCategories: "books"
    }
  }
);
~~~

Explain why you do not need to read the entire array on the client and reassign it.

### Exercise 8 – Server-side expressions

An Invoice has quantity = 2, unitPriceCents = 50000. Write an update pipeline computing amountCents = quantity × unitPriceCents. If quantity is modified concurrently, why is server-side computation better than reading quantity on the client and calling $set amountCents afterward?

### Exercise 9 – Idempotency key

A job must add rewardPoints +10 exactly once per jobId. A network timeout leaves the client unsure whether the write succeeded. Design a filter and update using appliedRewards so points are never added twice, and note the limitation when the marker array grows too large.

### Exercise 10 – Invariant across two documents

Account A has balanceCents = 100000, B has 50000. 20000 must be transferred. Why are two separate $inc calls not atomic together? When is a transaction needed? If a payment API must also be called, does the database transaction automatically cover the external API?

## 29. Design checklist before writing an update

Before building a write API under concurrency, ask in order:

1. Is the new value a **delta** or a **target value**? If delta, prefer $inc; if an extremum, $min/$max.
2. Is there an invariant that must hold **at write time**? Put the condition in the filter.
3. Are you computing from stale client-read data? Consider pipeline updates, CAS, or version.
4. Are multiple dependent fields in the same document? Combine them into one updateOne.
5. Does the write span multiple documents? Evaluate transactions/ledgers.
6. Can the command be retried after a timeout? Idempotency is needed.
7. Are you replacing an entire object or array? Update only the exact path when patching.
8. Do you need to distinguish success from conflict? Check matchedCount/modifiedCount.
9. Do you need the document returned after modification? Consider findOneAndUpdate.
10. Is there a hot document under many writers? Measure load and consider sharded counters.

## 30. Conclusion

Lost updates happen when multiple requests **read an old value and overwrite with a locally computed result**, causing another writer's change to vanish. In MongoDB, express transformations directly using **server-side atomic update operators** whenever suitable:

- **$inc** to increment/decrement without reading first.
- **$min/$max** to preserve lowest/highest thresholds without client-side comparison.
- **$addToSet/$pull** to modify arrays without reassigning a stale array copy.
- **$set with filters** for conditional state transitions.
- **CAS/version** to detect whether a document was modified after being read.
- **Update pipelines** to compute formulas from current fields.
- **findOneAndUpdate** when modifying and retrieving the before/after value in one operation.
- **Transactions or suitable idempotent/ledger architectures** when invariants cross multiple documents.

Two principles go hand in hand: **atomicity protects the operation's boundary**, while **business correctness** depends on filter conditions, version management, idempotency, and document boundaries. An atomic write does not by itself prevent negative stock, protect an entire two-account money transfer, or stop business retries from duplicating side effects.

## References

- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — $inc](https://www.mongodb.com/docs/manual/reference/operator/update/inc/)
- [MongoDB Manual — $min](https://www.mongodb.com/docs/manual/reference/operator/update/min/)
- [MongoDB Manual — $max](https://www.mongodb.com/docs/manual/reference/operator/update/max/)
- [MongoDB Manual — $addToSet](https://www.mongodb.com/docs/manual/reference/operator/update/addToSet/)
- [MongoDB Manual — $pull](https://www.mongodb.com/docs/manual/reference/operator/update/pull/)
- [MongoDB Manual — findOneAndUpdate](https://www.mongodb.com/docs/manual/reference/method/db.collection.findOneAndUpdate/)
- [MongoDB Manual — Updates with Aggregation Pipeline](https://www.mongodb.com/docs/manual/tutorial/update-documents-with-aggregation-pipeline/)
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Java Sync Driver — Update Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/update/)
