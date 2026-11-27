# Full Documents, Update Descriptions, and Before/After Data in Change Streams

## Lesson Objectives

In **Spring Data MongoDB**, change streams allow an application to receive events when documents are inserted, updated, replaced, or deleted without continuously polling the collection. However, a change event does not always contain the entire document state. For `update` events, MongoDB by default only returns a description of **which fields changed**; if you need the full document or the state **before and after** the change, you must choose the appropriate change stream option and meet MongoDB's support requirements.

This lesson belongs to the **Change stream** chapter and focuses on three groups of information:

1. `updateDescription`: a delta-style description of the change, including the new values of updated fields, the names of removed fields, and information about truncated arrays when applicable.
2. `fullDocument`: the full document after the operation or a re-read near the time the change event is processed, depending on the `fullDocument` mode.
3. `fullDocumentBeforeChange`: the **pre-image**, i.e., a snapshot of the document before the operation; combined with the post-image mode to compare exact before/after states when supported by the system.

We will use `mongosh` to observe BSON events, then use `ReactiveMongoTemplate` and `ChangeStreamOptions` to map the data in Java. Principles regarding resume tokens, latency, storage overhead, and missing-image errors also apply when using the MongoDB Java Driver or Spring Data's synchronous listener mechanism.

> **Prerequisites:** change streams require a supported MongoDB deployment, typically a replica set or sharded cluster; a standalone MongoDB instance does not meet this requirement. Pre/post-images were introduced in MongoDB **6.0** and must be enabled separately per collection. Spring Data examples using `getBodyBeforeChange()` and `fullDocumentBeforeChangeLookup(...)` are available in Spring Data MongoDB **4.0+**; verify the exact server, Java driver, and Spring Data versions of your project.

## 1. What Parts Does a Change Stream Event Have?

Suppose the `orders` collection stores orders:

```javascript
db.orders.insertOne({
  _id: "order-42",
  status: "CREATED",
  amount: 100,
  coupon: "WELCOME"
});
```

Open another `mongosh` terminal to watch changes **before performing the update**:

```javascript
const stream = db.orders.watch();

while (stream.hasNext()) {
  printjson(stream.next());
}
```

In the data-writing terminal, run:

```javascript
db.orders.updateOne(
  { _id: "order-42" },
  {
    $set: { status: "PAID", amount: 120 },
    $unset: { coupon: "" }
  }
);
```

An illustrative structure of the resulting event might look like this (with metadata omitted; real resume tokens are BSON values and vary):

```javascript
{
  _id: { _data: "<resume-token>" },
  operationType: "update",
  clusterTime: Timestamp(...),
  ns: { db: "shop", coll: "orders" },
  documentKey: { _id: "order-42" },
  updateDescription: {
    updatedFields: { status: "PAID", amount: 120 },
    removedFields: ["coupon"],
    truncatedArrays: []
  }
}
```

| Event field | Meaning | Notes |
| --- | --- | --- |
| `_id` | Resume token used to continue the stream at a known position | Not the order `_id`; must not be removed or modified in a pipeline |
| `operationType` | Event type: `insert`, `update`, `replace`, `delete`, ... | Determines which fields are meaningful |
| `clusterTime` | Logical timestamp associated with the operation in the oplog | Not the same as the time the application processes the event |
| `ns` | Database and collection namespace | Useful for routing in broad-scope streams |
| `documentKey` | Identifier of the affected document, including `_id` and possibly shard key info | Used to identify the changed record |
| `updateDescription` | Change description for `update` | Does not contain the full document or old field values |
| `fullDocument` | Full document when available or requested via the appropriate mode | May be absent or `null` on `update` |
| `fullDocumentBeforeChange` | Pre-image if enabled and requested | May be absent or `null` when no image is available |

**Do not confuse the three IDs:** `event._id` is the resume token; `documentKey._id` is the document's ID; `fullDocument._id` is the ID inside the full document (if present).

An event without a full body is not necessarily an error. For `update`, that is typically the default behavior to reduce data transfer volume.

## 2. Understanding updateDescription Properly

For an `update` operation, MongoDB typically provides:

```javascript
updateDescription: {
  updatedFields: { "status": "PAID", "amount": 120 },
  removedFields: ["coupon"],
  truncatedArrays: []
}
```

### updatedFields: new values of changed fields

`updatedFields` maps field paths to their **new values**. For `$set`, this is typically the newly assigned value; for `$inc`, it reflects the value after incrementing/decrementing, not the original `$inc` operation.

```javascript
db.orders.updateOne(
  { _id: "order-42" },
  { $inc: { amount: 10 } }
);

// Example corresponding delta (when amount was previously 120):
// updateDescription.updatedFields: { amount: 130 }
```

Therefore, from `updatedFields: { amount: 130 }` you **cannot deduce** that the previous amount was 120; you only know the post-update value. If business logic needs the exact difference, you must have the prior state (a pre-image, a separately managed snapshot, or another reliable data source).

For nested fields, keys are typically represented using dot notation:

```javascript
db.orders.updateOne(
  { _id: "order-42" },
  { $set: { "delivery.city": "Hanoi" } }
);

// Example:
// updatedFields: { "delivery.city": "Hanoi" }
```

If an actual field name contains a dot or a numeric-looking key that is ambiguous with an array element index, MongoDB may provide `updateDescription.disambiguatedPaths` to describe the path components. This field was added in MongoDB 6.1 and whether it is emitted depends on the server version and the `showExpandedEvents` option; you should not blindly split every key on dots and assume it is an unambiguous path.

### removedFields: names of deleted fields

`removedFields` contains a list of field paths that were removed, such as `["coupon"]` after `$unset`. It **does not contain the old values** of those fields. When you need to know which promo code was removed, you must read the pre-image or store history elsewhere.

### truncatedArrays: changes in array length

For certain aggregation-pipeline updates that shorten an array, MongoDB may return:

```javascript
updateDescription: {
  updatedFields: {},
  removedFields: [],
  truncatedArrays: [
    { field: "items", newSize: 2 }
  ]
}
```

`truncatedArrays` indicates the array name and its new size. Depending on how the update is written, MongoDB may also report the entire array as replaced inside `updatedFields` instead of reporting a separate truncation. Do not assume every array modification produces `truncatedArrays`.

### How update, replace, and delete differ

- `update`: typically has `updateDescription`; `fullDocument` depends on the stream option.
- `replace`: when replacing the entire document, the event carries `fullDocument` with the replacement content; do not rely on `updateDescription` as with field-level updates.
- `delete`: the document no longer exists, so there is no post-delete document to read. If a pre-image is available, `fullDocumentBeforeChange` gives the value right before deletion.
- `insert`: has `fullDocument` for the newly inserted record; there is no pre-image before insertion.

## 3. fullDocument: Default, updateLookup, and Post-Image

`fullDocument` has several key modes:

| `fullDocument` value | For update events | Requirements |
| --- | --- | --- |
| `"default"` | Usually does not return the full document; still includes the delta | Does not require enabling pre/post-images |
| `"updateLookup"` | Reads the currently existing document at lookup time, at majority-committed state; may be `null` | Does not require enabling pre/post-images |
| `"whenAvailable"` | Returns the **post-image tied to the event** if available; `null` when unavailable | MongoDB 6.0+ and pre/post-images enabled on the collection |
| `"required"` | Requires the post-image; throws an error if the image is unavailable | MongoDB 6.0+ and pre/post-images enabled on the collection |

`"default"` is the standard behavior. For `insert` and `replace`, the full document is available by the nature of the event; for `delete` there is no post-document.

### updateLookup: full document at re-read time

```javascript
const stream = db.orders.watch([], {
  fullDocument: "updateLookup"
});

while (stream.hasNext()) {
  const event = stream.next();
  printjson({
    operation: event.operationType,
    delta: event.updateDescription,
    currentDocument: event.fullDocument
  });
}
```

With `updateLookup`, MongoDB re-reads the **current majority-committed** version of the modified document. If the document is deleted before the lookup runs, `fullDocument` can be `null`. If another update happens quickly after the update that caused the event, the re-read version may already contain **later changes**:

```text
t1: order-42  status=CREATED
t2: update A  status=PAID      -> event A: updatedFields.status=PAID
t3: update B  status=SHIPPED   -> event B: updatedFields.status=SHIPPED
t4: lookup for event A         -> fullDocument.status may be SHIPPED
```

Thus, event A's `updateDescription` and the `fullDocument` from `updateLookup` can reflect **two different points in time**. This is not corrupted data, but rather a property of performing a re-read. Do not use `updateLookup` as absolute proof of the post-image *at the exact moment of the event* if concurrent writes occur.

In some rapid-deletion scenarios, filtering a change stream by a `fullDocument` field combined with `updateLookup` can also complicate resume token recovery; test your filter and resume mechanism rather than relying solely on the re-read body.

### whenAvailable and required: the event's post-image

After enabling pre/post-images, MongoDB can return the post-change content corresponding to the **exact operation** that triggered the event using `"whenAvailable"` or `"required"`. This is the right approach when you need the state immediately after the update, rather than the latest version at lookup time.

- `whenAvailable`: continues the stream when the image is missing; the application must handle `null`.
- `required`: errors the stream if the requested image is unavailable. Only use this when business logic strictly requires an image for every supported event and proper monitoring/recovery is in place.

## 4. Enabling and Reading Pre-Images/Post-Images in MongoDB 6.0+

A pre-image is the document **before** `update`, `replace`, or `delete`. A post-image is the document **after** `insert`, `update`, or `replace`. There is no pre-image for `insert` and no post-image for `delete`.

To enable image recording for an existing `orders` collection:

```javascript
db.runCommand({
  collMod: "orders",
  changeStreamPreAndPostImages: { enabled: true }
});
```

Enable this feature **before performing the changes you want to track**. MongoDB does not retroactively generate historical pre-images for updates/deletes that occurred before it was enabled.

In window A, open the stream and request both images:

```javascript
const stream = db.orders.watch([], {
  fullDocument: "whenAvailable",
  fullDocumentBeforeChange: "whenAvailable"
});

while (stream.hasNext()) {
  const event = stream.next();
  printjson({
    operationType: event.operationType,
    documentKey: event.documentKey,
    before: event.fullDocumentBeforeChange,
    delta: event.updateDescription,
    after: event.fullDocument,
    resumeToken: event._id
  });
}
```

In window B, run an update:

```javascript
db.orders.updateOne(
  { _id: "order-42" },
  {
    $set: { status: "SHIPPED", amount: 140 },
    $unset: { coupon: "" }
  }
);
```

Logical example of an update event, assuming the record immediately prior had `status: "PAID"`, `amount: 120`, and no `coupon`:

```javascript
{
  operationType: "update",
  documentKey: { _id: "order-42" },
  before: {
    _id: "order-42",
    status: "PAID",
    amount: 120
  },
  delta: {
    updatedFields: { status: "SHIPPED", amount: 140 },
    removedFields: [],
    truncatedArrays: []
  },
  after: {
    _id: "order-42",
    status: "SHIPPED",
    amount: 140
  },
  resumeToken: { _data: "<resume-token>" }
}
```

This is a **structural illustration**, not an actual execution output or a guarantee on BSON field ordering. In this operation `$unset` has no effect if `coupon` was already absent, so `removedFields` may be empty. If you want to test `removedFields`, set a new `coupon` value and then unset it in a subsequent update.

Next, test deleting:

```javascript
db.orders.deleteOne({ _id: "order-42" });
```

In a `delete` event, `fullDocument` no longer has an after-document; when the pre-image is available, `fullDocumentBeforeChange` contains the document right before deletion. Do not use `updateLookup` to try to fetch a deleted document: at lookup time, the record may no longer exist.

### Pre-image options

| `fullDocumentBeforeChange` | Behavior |
| --- | --- |
| `"off"` (default) | Do not request pre-image |
| `"whenAvailable"` | Return pre-image when available; may be `null` if missing |
| `"required"` | Return an error if the pre-image cannot be retrieved for an event that requires one |

For `"required"` to be meaningful, you must ensure the collection was configured before the updates/deletes occurred and that the image does not expire before the consumer reads it. Not all events (such as `insert` or `invalidate`) have the concept of a pre-image.

### Storage and limits to consider

Pre/post-images increase storage and processing overhead. Images can be purged according to retention policies and the oplog lifecycle. Enabling the option on a collection after changes have occurred does not backfill historical images; therefore `whenAvailable` must be handled as data that can be missing. `required` turns missing images into an error requiring intervention.

A single change event has a **16 MiB** BSON size limit. If you request the pre-image, post-image, and a large change description together, the total payload may exceed this threshold even though each individual document is valid. Be especially cautious with documents approaching 16 MiB and frequently updated collections. For systems requiring long-term audit trails, image retention policies do not replace a dedicated audit log or business history store.

## 5. Mapping in Spring Data MongoDB

In Spring Data MongoDB, `ChangeStreamOptions` chooses how the server supplies documents, while `ChangeStreamEvent<T>` provides the mapped data along with the raw event from the Java driver.

### Entity and observation DTO

Example of a simple entity (placed in `OrderSnapshot.java`):

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderSnapshot(
    @Id String id,
    String status,
    Integer amount,
    String coupon
) {}
```

Internal DTO for the consumer (placed in `OrderChange.java`):

```java
import java.util.List;
import org.bson.BsonDocument;
import org.bson.BsonValue;
import com.mongodb.client.model.changestream.OperationType;

public record OrderChange(
    OperationType operationType,
    BsonValue resumeToken,
    OrderSnapshot before,
    OrderSnapshot after,
    BsonDocument updatedFields,
    List<String> removedFields
) {}
```

`OrderSnapshot` represents a full state when present, whereas `OrderChange` holds both states and the delta. Both `before` and `after` **can be null**, depending on the operation and stream options. The example does not persist the resume token to a file; `BsonValue` is kept intact in the processing layer to avoid losing information through conversion.

### ReactiveMongoTemplate: retrieving before/after bodies and delta

```java
import java.util.List;

import com.mongodb.client.model.changestream.FullDocument;
import com.mongodb.client.model.changestream.FullDocumentBeforeChange;
import com.mongodb.client.model.changestream.UpdateDescription;
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import org.springframework.data.mongodb.core.ChangeStreamOptions;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class OrderChangeService {

    private final ReactiveMongoTemplate template;

    public OrderChangeService(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Flux<OrderChange> changes() {
        ChangeStreamOptions options = ChangeStreamOptions.builder()
            .fullDocumentLookup(FullDocument.WHEN_AVAILABLE)
            .fullDocumentBeforeChangeLookup(
                FullDocumentBeforeChange.WHEN_AVAILABLE
            )
            .build();

        return template.changeStream(
            "orders", options, OrderSnapshot.class
        ).map(this::toChange);
    }

    private OrderChange toChange(ChangeStreamEvent<OrderSnapshot> event) {
        var raw = event.getRaw();
        UpdateDescription delta =
            raw == null ? null : raw.getUpdateDescription();

        return new OrderChange(
            event.getOperationType(),
            event.getResumeToken(),
            event.getBodyBeforeChange(),
            event.getBody(),
            delta == null ? null : delta.getUpdatedFields(),
            delta == null || delta.getRemovedFields() == null
                ? List.of()
                : delta.getRemovedFields()
        );
    }
}
```

In the code above:

- `fullDocumentLookup(FullDocument.WHEN_AVAILABLE)` requests the **post-image** if available. You can replace it with `FullDocument.UPDATE_LOOKUP` if you need to read the current document without pre/post-images enabled; the two have different point-in-time semantics.
- `fullDocumentBeforeChangeLookup(FullDocumentBeforeChange.WHEN_AVAILABLE)` requests the pre-image. If you want a missing image to fail the stream, use `FullDocumentBeforeChange.REQUIRED`.
- `event.getBody()` maps from `fullDocument`; `event.getBodyBeforeChange()` maps from `fullDocumentBeforeChange`. The before-change API has been available since Spring Data MongoDB 4.0.
- `event.getRaw()` returns the MongoDB Java driver's `ChangeStreamDocument<Document>`; `getUpdateDescription()` retrieves the delta for `update`. In other events, the delta may be `null`.
- `event.getResumeToken()` is used to store the position for resuming the stream. The token is BSON; when persisting long-term, preserve its structure and data types.
- `Flux` does not actually receive events until subscribed. A change stream can be long-lived; place it under a managed consumer lifecycle rather than creating a new subscription per HTTP request.

If you do not yet need pre-images, you can read the current document on updates:

```java
ChangeStreamOptions options = ChangeStreamOptions.builder()
    .returnFullDocumentOnUpdate()
    .build();

// Equivalent to selecting fullDocumentLookup(FullDocument.UPDATE_LOOKUP).
```

**Accuracy warning:** `returnFullDocumentOnUpdate()` is convenient for rebuilding a read model to a near-current state, but its `getBody()` may reflect changes that occurred **after** the `updateDescription` in that event.

### Reading directly from the MongoDB Java Driver

When you need to inspect the BSON structure without Spring Data's conversion:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.changestream.FullDocument;
import com.mongodb.client.model.changestream.FullDocumentBeforeChange;
import org.bson.Document;

MongoCollection<Document> orders =
    mongoClient.getDatabase("shop").getCollection("orders");

var cursor = orders.watch()
    .fullDocument(FullDocument.WHEN_AVAILABLE)
    .fullDocumentBeforeChange(FullDocumentBeforeChange.WHEN_AVAILABLE)
    .iterator();

try (cursor) {
    while (cursor.hasNext()) {
        var event = cursor.next();
        System.out.println("operation=" + event.getOperationType());
        System.out.println("delta=" + event.getUpdateDescription());
        System.out.println("before=" + event.getFullDocumentBeforeChange());
        System.out.println("after=" + event.getFullDocument());
    }
}
```

This example assumes an initialized and validly connected `mongoClient` of type `com.mongodb.client.MongoClient`. This is a thread-blocking loop, suitable for demonstrations or a dedicated worker with cursor-closing mechanics; do not place it directly on an HTTP request-handling thread. For reactive Spring Data applications, `ReactiveMongoTemplate` helps integrate subscription lifecycle, backpressure, and error handling with Reactor.

## 6. Choosing the Right Data for Your Use Case

| Need | What to read | Why |
| --- | --- | --- |
| Send an "order status changed" notification | `updateDescription.updatedFields` | Compact, avoids re-reading the entire document |
| Update a cache/read model with current state | `fullDocument: "updateLookup"` or post-image | Needs the body; clearly define point-in-time requirements |
| Compute the exact difference **before and after an update** | Pre-image + post-image | Two event-bound images, if supported and available |
| Audit: know the value removed by `$unset` | `fullDocumentBeforeChange` | `removedFields` only contains field names |
| Display a newly `insert`ed record | Default `fullDocument` | Insert events already contain the inserted document |
| Record a newly `delete`d document | `fullDocumentBeforeChange` | No post-document remains after deletion |
| Only count event statistics | `operationType`, `documentKey`, metadata | Avoids unnecessary image overhead |

Regardless of the option chosen, received data must still pass authorization and security checks. Pre-images may contain values that were deleted or hidden from the current UI; do not automatically dump raw pre/post-images into public logs or send them over WebSockets.

## 7. Resume Tokens, Processing Order, and Operations

A long-running consumer typically must:

1. Receive an event and extract the original resume token from `ChangeStreamEvent.getResumeToken()`.
2. Perform business processing or write to an outbox/queue according to the designed model.
3. **Persist the checkpoint token only after the side effect has been safely processed**. If you checkpoint before processing, a crash can cause you to miss re-running the event.
4. On restart, pass the stored token via `ChangeStreamOptions.builder().resumeAfter(token).build()` (or the driver's equivalent resume mechanism) to continue, provided the token is still valid within the oplog retention window.
5. Design side effects to be **idempotent** by event/business identifier, because a failure between processing and checkpointing can cause an event to be reprocessed.

Store the token with its exact BSON types; do not convert it to a display string and parse it back arbitrarily. Do not remove or alter `_id` of the change event in the pipeline, because that is the resume token; mutating `_id` can cause the stream to fail.

### Important limitations

- **Not a full collection snapshot:** `watch` only receives changes within the stream's scope and point in time; if you need the initial existing data, you must combine it with a snapshot/initial load procedure.
- **Not an infinitely retained queue:** resuming depends on the oplog, collection state, and token validity; if the application stops for too long, you must have a resynchronization strategy.
- **No default end-to-end exactly-once:** the consumer may re-execute side effects on retry. Checkpointing and idempotency are required.
- **No guarantee of pre/post-images if not enabled or expired:** pay special attention to events emitted before configuration.
- **No guarantee of event-time accuracy for lookup:** `updateLookup` reads the current majority-committed version, which may be a newer state.
- **Not suitable as a replacement for legally binding transactions/audit logs:** for mandatory historical retention, consider recording durable business events in a dedicated transaction/outbox.

### Common issues

| Symptom | Possible cause | Diagnosis and resolution |
| --- | --- | --- |
| `getBody() == null` on update event | Using default mode, lookup found nothing, or post-image missing | Check `fullDocument` option and image availability |
| `getBodyBeforeChange() == null` | Not requested, images not enabled, inapplicable event type, or image expired | Check `collMod`, version, and when the event occurred |
| Stream errors when using `REQUIRED` | Requested pre/post-image no longer exists | Verify retention and recovery/resync strategy |
| `updateDescription == null` | `insert`, `replace`, `delete`, or non-update event | Branch by `operationType` |
| `updatedFields` lacks old value | Delta only stores post-change values | Use pre-image or separate history storage |
| `fullDocument` differs from delta | A later update occurred before `updateLookup` ran | Use post-image if an exact snapshot is needed |
| Cannot open stream | Standalone server or unsupported deployment/role | Check topology, `changeStream` privilege, and version |
| Slow consumer, invalid token | Oplog or image data no longer covers recovery | Monitor lag, checkpoint, and prepare initial resync |
| No events received despite writes | `Flux` not subscribed or watcher opened after the write | Ensure active subscription and generate a new change afterward |
| Payload too large | Full document plus before/after images exceed 16 MiB limit | Reduce document size or request fewer images |

## 8. Practice and Verification

**Exercise 1 — Delta:** Run the default watcher, perform `$set`, `$inc`, `$unset`, and update a nested field. Print `updatedFields` and `removedFields`. Explain why the delta does not reveal the old values.

**Exercise 2 — updateLookup:** Enable `fullDocument: "updateLookup"`. Perform two consecutive updates on the same document and observe `fullDocument` alongside `updateDescription`. Explain why they can differ, even if the difference does not appear in a single test run due to timing.

**Exercise 3 — Pre/post-images:** On a MongoDB 6.0+ replica set, enable `changeStreamPreAndPostImages`, run a watcher with both options set to `whenAvailable`. Perform `update`, `replace`, and `delete`, and fill out a table: operation, before, delta, after. Indicate which fields can be `null`.

**Exercise 4 — REQUIRED and retention:** Try `fullDocumentBeforeChange: "required"` in a test environment, and observe behavior if the pre-image is missing or an event was generated before enabling the feature. Explain how the application should handle the error instead of silently ignoring it.

**Exercise 5 — Spring Data:** Complete `OrderChangeService`, write a consumer receiving `OrderChange`, and save checkpoints safely. Simulate a restart and verify idempotency of event processing. Do not save the token before side effects complete.

### Completion checklist

- Able to distinguish `documentKey._id` from the resume token `event._id`.
- Correctly state the meaning of `updatedFields`, `removedFields`, `truncatedArrays`, and their limitations regarding old values.
- Explain why `updateLookup` may read a version newer than when the event occurred.
- Distinguish `whenAvailable` from `required` for pre/post-images, and know the MongoDB 6.0+ requirement.
- Identify which data may be missing for `insert`, `update`, `replace`, and `delete`.
- Use `ChangeStreamOptions`, `getBody()`, `getBodyBeforeChange()`, `getRaw()`, and `getResumeToken()` appropriately.
- Design a consumer with checkpoints, duplicate handling, and protection against exposing sensitive images externally.

## References

- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changestreams/)
- [MongoDB Manual — `$changeStream` Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/changestream/)
- [MongoDB Manual — `db.collection.watch()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.watch/)
- [MongoDB Manual — Update Change Event](https://www.mongodb.com/docs/manual/reference/change-events/update/)
- [MongoDB Java Sync Driver — Change Streams](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/change-streams/)
- [Spring Data MongoDB — `ChangeStreamOptions.ChangeStreamOptionsBuilder` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ChangeStreamOptions.ChangeStreamOptionsBuilder.html)
- [Spring Data MongoDB — `ChangeStreamEvent<T>` API](https://docs.spring.io/spring-data/data-mongodb/reference/api/java/org/springframework/data/mongodb/core/ChangeStreamEvent.html)
- [Spring Data MongoDB — `ReactiveMongoOperations` API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/ReactiveMongoOperations.html)
