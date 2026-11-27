# BSON Binary, UUID, and UUID Representation Conventions Across MongoDB Drivers

MongoDB stores documents using **BSON (Binary JSON)**. In addition to types like string, number, date, and ObjectId, BSON provides the **Binary** type for arbitrary byte sequences. **UUID (Universally Unique Identifier)** is a specialized application of the Binary type: a 128-bit identifier commonly written as a hyphenated string, yet stored compactly in BSON as 16 bytes.

The subtle trap when working with UUIDs is that **two values that look identical as strings are not necessarily stored the same way in MongoDB**. Older drivers used different byte orderings and different BSON binary subtypes. Consequently, when Java, Python, C#, or Node.js services share a collection, applications must standardize how UUIDs are written and read.

This lesson explains the Binary structure, standard UUID, legacy UUIDs, how drivers represent UUIDs, the consequences of inconsistent configuration, and how to handle legacy data safely.

## 1. Distinguishing Binary, UUID, and UUID Strings

These three representations can describe the exact same business identifier, yet they are **different BSON types or subtypes**:

| Representation | Content | How MongoDB Sees It |
| --- | --- | --- |
| String | "00112233-4455-6677-8899-aabbccddeeff" | BSON string |
| Binary subtype 4 | 16 bytes in standard UUID byte order | BSON Binary, UUID standard |
| Binary subtype 3 | 16 bytes in legacy UUID convention | BSON Binary, UUID legacy |

Example document storing a UUID as a string:

~~~javascript
{
  sessionId: "00112233-4455-6677-8899-aabbccddeeff",
  userId: "user-101",
  status: "ACTIVE"
}
~~~

Another document storing a UUID as standard BSON Binary:

~~~javascript
{
  sessionId: UUID("00112233-4455-6677-8899-aabbccddeeff"),
  userId: "user-101",
  status: "ACTIVE"
}
~~~

In **mongosh**, the **`UUID(...)`** helper constructs a UUID as BSON Binary **subtype 4**. These two documents do not share the same BSON type for **sessionId**. Therefore, querying with a string is not automatically equivalent to querying with a binary UUID:

~~~javascript
// Matches BSON string value.
db.sessions.find({
  sessionId: "00112233-4455-6677-8899-aabbccddeeff"
});

// Matches BSON Binary UUID standard value.
db.sessions.find({
  sessionId: UUID("00112233-4455-6677-8899-aabbccddeeff")
});
~~~

MongoDB does not automatically coerce a UUID string into a BSON Binary UUID during normal equality matching.

### Why Store UUIDs as Binary?

A UUID is 128 bits, equivalent to **16 bytes of identifier data**. Its familiar text form has 32 hex characters and 4 hyphens, totaling 36 characters. Binary stores the 16 identifier bytes directly, whereas a string stores text characters along with BSON string overhead.

However, Binary does not automatically solve key selection, randomness, sortability, or data distribution concerns. Index size and insert behavior still depend on schema design, UUID version, key values, and workload.

## 2. What Is the Structure of BSON Binary?

BSON defines the **Binary Data** element type, typically denoted by type code **0x05**. A Binary value carries two main pieces of metadata/payload:

1. **Payload**: the actual sequence of bytes to store.
2. **Subtype**: a code indicating the convention under which those bytes should be interpreted.

You can visualize a Binary field as follows:

~~~text
BSON Document
└── field: "payload"
    ├── BSON type: Binary (0x05)
    └── Binary value
        ├── byte length
        ├── subtype
        └── raw bytes
~~~

The length and subtype are encoded inside the BSON format. In reality, BSON Binary also has specific length-encoding rules; for this lesson, the key takeaway is that **the subtype is part of the Binary value itself**, not a separate business field stored next to the payload.

### Common Binary Subtypes

| Subtype | Common Name | Purpose |
| --- | --- | --- |
| **0x00** | Generic Binary | General-purpose binary data |
| **0x02** | Old Binary | Legacy binary representation; avoid for new data |
| **0x03** | UUID (Legacy) | UUIDs written under legacy driver conventions |
| **0x04** | UUID (Standard) | 16-byte UUID in standard byte order |
| **0x05** | MD5 | Data under the dedicated MD5 subtype |
| **0x06** | Encrypted BSON value | Data used by supported BSON encryption mechanisms |
| **0x80–0xFF** | User-defined | Application-defined subtype range |

This table focuses on subtypes relevant for distinguishing Binary and UUID; MongoDB specifies additional subtypes for specialized features.

**Subtype is not a security mechanism.** Having subtype `0x06` does not mean arbitrary Binary values are encrypted. Choose the subtype strictly according to the format and feature your application uses.

### When to Use Binary in General?

Binary suits reasonably sized payloads such as hashes, signatures, protocol frames, or raw byte sequences that the application must preserve verbatim. Illustrative example:

~~~javascript
{
  fileName: "avatar.png",
  checksum: BinData(0, "AQIDBA==")
}
~~~

**`AQIDBA==`** is the Base64 representation of the four bytes **01 02 03 04**; **`BinData(0, ...)`** in mongosh represents generic Binary subtype 0.

This is only a tiny-payload example. Standard BSON documents have a **16 MiB** size limit. When storing large files, consider **GridFS** or an appropriate file storage system; never stuff arbitrary files into unbounded Binary fields inside documents.

## 3. What Is a UUID?

A **UUID** is a 128-bit identifier commonly used to identify a session, business entity, event, or resource across multiple systems.

Example:

~~~text
00112233-4455-6677-8899-aabbccddeeff
~~~

The canonical text format has five hex groups following the pattern:

~~~text
8 chars - 4 chars - 4 chars - 4 chars - 12 chars
xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
~~~

A UUID carries a **version** and **variant** per the applicable standard. There are multiple UUID versions, such as random-based UUID v4 and time-ordered UUID v7. MongoDB Binary subtype 4 only defines how the UUID's **bytes are represented** in BSON; subtype 4 does not itself indicate which UUID version was generated.

### UUID Is Not ObjectId

MongoDB typically auto-generates an **ObjectId** for the **`_id`** field if the client omits it. ObjectId and UUID are two distinct types:

| Characteristic | ObjectId | UUID |
| --- | --- | --- |
| Payload size | 12 bytes | 16 bytes |
| mongosh representation | ObjectId("...") | UUID("...") |
| BSON type | ObjectId | Binary subtype 4 when standard is used |
| Usable as `_id` | Yes | Yes |
| Auto-generated when `_id` is omitted | Normally ObjectId | Must be chosen/generated explicitly by application or driver |

You can use UUID for **`_id`**:

~~~javascript
db.sessions.insertOne({
  _id: UUID("00112233-4455-6677-8899-aabbccddeeff"),
  userId: "user-101",
  createdAt: new Date()
});
~~~

MongoDB does not force **`_id`** to be an ObjectId. However, if you use UUID as **`_id`**, standardize the BSON representation upfront because `_id` cannot be changed via standard update operations.

### UUID Is Not a Login Token

UUIDs provide identification, not implicit proof of authentication or authorization. Even when UUIDs are randomly generated, applications must still authenticate users and enforce authorization when accessing UUID-keyed resources. Never treat "hard-to-guess IDs" as your sole security layer.

## 4. Standard UUID: Binary Subtype 4 and Byte Order

In the modern representation, a UUID is stored as **BSON Binary subtype 4 (0x04)** with the exact **16 bytes in standard UUID byte order**.

Take the sample UUID:

~~~text
00112233-4455-6677-8899-aabbccddeeff
~~~

Strip the hyphens and read each pair of hex digits as one byte:

~~~text
00 11 22 33 44 55 66 77 88 99 aa bb cc dd ee ff
~~~

This is the standard byte order when writing subtype 4 UUIDs. Hyphens exist only in the text display format; they are not stored inside the 16 Binary bytes.

~~~text
UUID string:
  00112233-4455-6677-8899-aabbccddeeff
      |
      | convert hex pairs into bytes
      v
BSON UUID standard payload:
  00 11 22 33 44 55 66 77 88 99 aa bb cc dd ee ff

Subtype:
  0x04
~~~

In mongosh:

~~~javascript
const id = UUID("00112233-4455-6677-8899-aabbccddeeff");

db.sessions.insertOne({
  sessionId: id,
  status: "ACTIVE"
});

db.sessions.findOne({ sessionId: id });
~~~

**The same standard UUID** produces the exact same 16-byte payload and subtype 4 across all drivers adhering to the standard UUID representation, regardless of language-specific UUID class names.

## 5. Why Does Legacy UUID Subtype 3 Exist?

Early MongoDB drivers did not agree on how to encode UUIDs into BSON Binary. Several drivers used **subtype 3 (0x03)** and chose byte orders matching their language's native UUID/GUID layout.

The complication spans two dimensions:

- **Subtype**: legacy subtype 3 differs from standard subtype 4.
- **Byte order**: across legacy drivers, the 16 bytes could be arranged differently.

Therefore, inspecting a Binary subtype 3 value alone is **insufficient** to determine the original UUID string reliably. You need to know which driver wrote the data and what UUID representation was configured at write time.

### Four Important Conventions

Common names in MongoDB drivers and documentation:

| Convention | BSON Subtype | 16-Byte Order | Meaning |
| --- | --- | --- | --- |
| **STANDARD** | 4 | Standard UUID byte order | Recommended for all new data |
| **PYTHON_LEGACY** | 3 | Standard UUID byte order | Same payload as STANDARD, different subtype |
| **JAVA_LEGACY** | 3 | Reverses bytes within each 8-byte half | Legacy Java driver convention |
| **CSHARP_LEGACY** | 3 | Little-endian in the first three GUID components | Legacy .NET/C# driver convention |

Using the same sample UUID string:

~~~text
00112233-4455-6677-8899-aabbccddeeff
~~~

The differences can be shown concretely:

| Representation | Subtype | Hex Payload (16 bytes) |
| --- | --- | --- |
| STANDARD | 04 | 00 11 22 33 44 55 66 77 88 99 aa bb cc dd ee ff |
| PYTHON_LEGACY | 03 | 00 11 22 33 44 55 66 77 88 99 aa bb cc dd ee ff |
| JAVA_LEGACY | 03 | 77 66 55 44 33 22 11 00 ff ee dd cc bb aa 99 88 |
| CSHARP_LEGACY | 03 | 33 22 11 00 55 44 77 66 88 99 aa bb cc dd ee ff |

The bytes in the table are computed from the sample UUID string. **JAVA_LEGACY**, **CSHARP_LEGACY**, and **PYTHON_LEGACY** are **UUID encoding convention names**, not claims that current Java/C#/Python driver versions still default to legacy formats.

### 5.1. PYTHON_LEGACY

PYTHON_LEGACY stores the 16 bytes in standard order but uses subtype 3:

~~~text
String:  00112233-4455-6677-8899-aabbccddeeff
Bytes:   00 11 22 33 44 55 66 77 88 99 aa bb cc dd ee ff
Subtype: 03
~~~

The subtle hazard: the byte payload matches STANDARD, yet MongoDB treats it as a distinct Binary value because **subtype 03 ≠ subtype 04**.

### 5.2. JAVA_LEGACY

JAVA_LEGACY reverses the byte order within **each 8-byte half**:

~~~text
STANDARD:
  00 11 22 33 44 55 66 77 | 88 99 aa bb cc dd ee ff

JAVA_LEGACY:
  77 66 55 44 33 22 11 00 | ff ee dd cc bb aa 99 88
~~~

Java's `UUID` class itself does not carry the wrong byte order. This is **how the legacy BSON UUID convention serialized UUIDs into Binary**, so reading old data correctly requires selecting the matching representation.

### 5.3. CSHARP_LEGACY

The CSHARP_LEGACY convention stems from the traditional byte layout of **`System.Guid`**:

~~~text
UUID:
  00112233-4455-6677-8899-aabbccddeeff

STANDARD:
  00 11 22 33 | 44 55 | 66 77 | 88 99 aa bb cc dd ee ff

CSHARP_LEGACY:
  33 22 11 00 | 55 44 | 77 66 | 88 99 aa bb cc dd ee ff
~~~

The first 4-byte group, second 2-byte group, and third 2-byte group have their endianness reversed; the final 8 bytes remain unchanged. This explains why a GUID written by an older .NET driver can decode into a completely different UUID if another tool misinterprets it using standard byte order.

## 6. Two Classic Compatibility Failures

### 6.1. Same Logical UUID, Different BSON Binary

Suppose Application A writes a standard UUID:

~~~text
Representation: STANDARD
Subtype:        04
Payload:        00 11 22 33 44 55 66 77 88 99 aa bb cc dd ee ff
~~~

Application B writes the same UUID using PYTHON_LEGACY:

~~~text
Representation: PYTHON_LEGACY
Subtype:        03
Payload:        00 11 22 33 44 55 66 77 88 99 aa bb cc dd ee ff
~~~

Even with identical byte payloads, the BSON values have **different subtypes**. An equality query using UUID subtype 4 will not match documents stored with subtype 3.

If **sessionId** has a unique index, do not expect the index to unify different UUID representations into one logical identifier. Binary values with different subtypes or byte layouts are not recognized as BSON duplicates.

### 6.2. Same 16 Bytes, Decoded Into a Different UUID

Suppose a JAVA_LEGACY payload is read using a STANDARD decoder unaware of the legacy convention:

~~~text
Payload read from database:
  77 66 55 44 33 22 11 00 ff ee dd cc bb aa 99 88
~~~

For JAVA_LEGACY source data, this payload represents the original UUID:

~~~text
00112233-4455-6677-8899-aabbccddeeff
~~~

If a tool interprets those raw bytes as standard order, the resulting text becomes:

~~~text
77665544-3322-1100-ffee-ddccbbaa9988
~~~

Modern libraries may **refuse** to decode an incompatible subtype rather than silently returning a corrupted UUID. Exact behavior depends on the driver and configuration. The core lesson remains: **you cannot guess the representation solely from the application-level UUID format**.

## 7. Reading Binary in mongosh and Extended JSON

In mongosh, a standard UUID value can be constructed via:

~~~javascript
UUID("00112233-4455-6677-8899-aabbccddeeff")
~~~

When serialized to canonical **Extended JSON**, BSON Binary data typically has the structure:

~~~json
{
  "sessionId": {
    "$binary": {
      "base64": "ABEiM0RVZneImaq7zN3u/w==",
      "subType": "04"
    }
  }
}
~~~

In this representation:

- **base64** encodes the byte payload as text so it can travel inside JSON.
- **subType** is the subtype code as a hex string; **04** corresponds to UUID standard.
- The JSON document is only a **text representation** of Binary; BSON stores the raw byte payload directly, not a Base64 business string.

Changing **subType** to **03** without changing the bytes produces a Binary value with the same payload and legacy subtype. Flipping the subtype alone is **not a general-purpose legacy UUID migration method**, because JAVA_LEGACY and CSHARP_LEGACY also require byte reordering.

In mongosh, you can inspect the canonical Extended JSON of a document:

~~~javascript
const document = db.sessions.findOne({ status: "ACTIVE" });

print(
  EJSON.stringify(document, null, 2, { relaxed: false })
);
~~~

Actual output depends on the document and stored types. When inspecting data imported from legacy systems, record **both the subtype and raw bytes**, then cross-check against the representation used by the source driver.

### Checking Whether a Field Is Binary

~~~javascript
db.sessions.find({
  sessionId: { $type: "binData" }
});
~~~

The **`$type: "binData"`** predicate filters for the BSON Binary type in general. It does not prove the value is standard UUID subtype 4; generic Binary, legacy UUIDs, and other subtypes also match `"binData"`.

## 8. UUID Conventions in Modern Drivers

Each language ecosystem has its own UUID type:

| Ecosystem | Application UUID Type | MongoDB Storage Under Standard |
| --- | --- | --- |
| Java | `java.util.UUID` | BSON Binary subtype 4 when codec is configured to STANDARD |
| Python | `uuid.UUID` | BSON Binary subtype 4 when `uuidRepresentation` is STANDARD |
| .NET/C# | `System.Guid` | BSON Binary subtype 4 when serializer uses `GuidRepresentation.Standard` |
| Node.js | Driver BSON `UUID` | BSON Binary subtype 4 |
| mongosh | `UUID("...")` | BSON Binary subtype 4 |

Rule for new systems: **use STANDARD / subtype 4 consistently across writers, readers, and query filters**.

Never treat a language name as proof of which representation is in use. Modern drivers may have different defaults from older drivers; even across versions of the same language driver, automatic UUID conversion behavior can change. When interacting with existing data, verify **driver version, serializer/codec configuration, and actual stored bytes**.

### 8.1. Java Sync Driver: Configuring STANDARD

The following Java snippet demonstrates configuring **`MongoClientSettings`** to serialize **`java.util.UUID`** as BSON Binary subtype 4.

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;

import org.bson.Document;
import org.bson.UuidRepresentation;

import java.util.UUID;

public class StandardUuidExample {

    public static void main(String[] args) {
        String uri = "mongodb://localhost:27017";

        MongoClientSettings settings = MongoClientSettings.builder()
                .applyConnectionString(new ConnectionString(uri))
                .uuidRepresentation(UuidRepresentation.STANDARD)
                .build();

        UUID sessionId =
                UUID.fromString("00112233-4455-6677-8899-aabbccddeeff");

        try (MongoClient client = MongoClients.create(settings)) {
            MongoDatabase database = client.getDatabase("demo");
            MongoCollection<Document> sessions =
                    database.getCollection("sessions");

            sessions.insertOne(
                    new Document("sessionId", sessionId)
                            .append("status", "ACTIVE")
            );

            Document result = sessions.find(
                    Filters.eq("sessionId", sessionId)
            ).first();

            System.out.println(result);
        }
    }
}
~~~

Key points to notice:

- **`UUID.fromString(...)`** instantiates a UUID in Java memory.
- **`UuidRepresentation.STANDARD`** governs UUID encoding/decoding between Java and BSON.
- **`Filters.eq(...)`** applies the same UUID representation when the driver serializes the query predicate.
- If the database previously stored that field using **JAVA_LEGACY subtype 3**, a STANDARD query will not automatically match the legacy records.

Modern Java Driver releases default to modes such as **UNSPECIFIED** to prevent ambiguous UUID interpretation. If an application fails to encode **`java.util.UUID`** due to an unspecified representation, configure it explicitly rather than guessing subtypes from bytes.

**Operational note:** This example assumes MongoDB is running on localhost, the user has write privileges, and the MongoDB Java Sync Driver dependency is included. Running it repeatedly inserts a new document each time because **sessionId** is not yet constrained by a unique index.

### 8.2. Python / PyMongo: Configuring CodecOptions

In Python, **`uuid.UUID`** is the application-level object type. In modern PyMongo, declare the representation explicitly on the target collection.

~~~python
from uuid import UUID

from bson.binary import UuidRepresentation
from bson.codec_options import CodecOptions
from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017")
database = client.get_database("demo")

sessions = database.get_collection(
    "sessions",
    codec_options=CodecOptions(
        uuid_representation=UuidRepresentation.STANDARD
    )
)

session_id = UUID("00112233-4455-6677-8899-aabbccddeeff")

sessions.insert_one({
    "sessionId": session_id,
    "status": "ACTIVE"
})

document = sessions.find_one({"sessionId": session_id})
print(document)
~~~

**`CodecOptions`** instructs PyMongo how to encode and decode UUIDs. For legacy data stored using PYTHON_LEGACY, JAVA_LEGACY, or CSHARP_LEGACY, select the matching convention when reading or migrating records.

PyMongo also lets you work directly with **`bson.binary.Binary`** to encode or decode a UUID under a specific representation:

~~~python
from uuid import UUID

from bson.binary import Binary, UuidRepresentation

original = UUID("00112233-4455-6677-8899-aabbccddeeff")

legacy_binary = Binary.from_uuid(
    original,
    uuid_representation=UuidRepresentation.JAVA_LEGACY
)

print(legacy_binary.subtype)  # 3
print(
    legacy_binary.as_uuid(
        uuid_representation=UuidRepresentation.JAVA_LEGACY
    )
)
~~~

This example creates and reads a Binary value solely in memory. It illustrates the rule: **know the representation when decoding**. Never see subtype 3 and automatically assume all records are JAVA_LEGACY.

### 8.3. Node.js: BSON UUID

The MongoDB Node.js Driver provides the **`UUID`** type, which can be used directly in inserts and queries.

~~~javascript
import { MongoClient, UUID } from "mongodb";

const client = new MongoClient("mongodb://localhost:27017");

async function main() {
  const sessionId = new UUID(
    "00112233-4455-6677-8899-aabbccddeeff"
  );

  await client.connect();

  try {
    const collection = client
      .db("demo")
      .collection("sessions");

    await collection.insertOne({
      sessionId,
      status: "ACTIVE"
    });

    const document = await collection.findOne({
      sessionId
    });

    console.log(document);
  } finally {
    await client.close();
  }
}

main().catch(console.error);
~~~

Node.js's BSON `UUID` type corresponds to standard UUID. When Java or Python services also access the database, all drivers must agree on **subtype 4**, not just on the UUID string logged by applications.

If a Node.js app passes a raw 16-byte **`Buffer`**, do not assume the driver automatically recognizes it as a UUID. Use the proper `UUID` class or configure BSON Binary/subtype explicitly. A generic `Buffer` and a UUID convey different data intents.

### 8.4. C# / .NET: Mind `GuidRepresentation`

.NET uses **`System.Guid`**. In older driver versions, GUID representation differed from standard UUID in both byte order and subtype. Therefore, .NET systems connecting to legacy data must check:

- Was the data written with **CSHARP_LEGACY** or **STANDARD**?
- What is the **`GuidSerializer`** / **`GuidRepresentation`** configuration of the running driver version?
- Are entity/POCO fields, filter predicates, and migration tools all using the same representation?

For greenfield systems, select **`GuidRepresentation.Standard`** for BSON UUID data; for existing systems, audit actual stored records before changing configuration.

Serializer APIs and configuration hooks can change across MongoDB .NET Driver releases. Do not copy legacy driver configuration options into newer driver versions without checking version documentation.

## 9. Read and Write Configurations Must Align

A multi-service architecture can run into the following mismatch:

~~~text
Java Service
  java.util.UUID ── STANDARD ──> subtype 04

Python Service
  uuid.UUID ── PYTHON_LEGACY ──> subtype 03

.NET Service
  System.Guid ── CSHARP_LEGACY ──> subtype 03, different byte order

MongoDB collection: sessions
  sessionId has multiple BSON representations
~~~

The resulting symptoms include:

1. Service A inserts a document successfully, yet Service B queries with the equivalent UUID string and finds nothing.
2. Some documents decode into the wrong UUID if the wrong byte-order convention is applied.
3. Query filters or unique indexes behave unexpectedly due to differing subtypes or byte payloads.
4. Exporting JSON converts UUIDs to strings or Extended JSON Binary depending on the tool.
5. A migration may "succeed" at the write layer yet corrupt identifiers if it changes only the subtype without reordering bytes.

### Conventions Should Be Documented Explicitly in the Data Contract

Example internal schema specification:

~~~yaml
collection: sessions
fields:
  sessionId:
    meaning: "Session identifier"
    logicalType: UUID
    bsonType: binData
    binarySubtype: "04"
    uuidRepresentation: STANDARD
    required: true
    indexed: true
~~~

This YAML snippet is an **illustrative design specification**, not a MongoDB command that automatically creates a collection or schema validator. It documents what all services must agree upon.

If a system standardizes on UUID strings at the database layer, explicitly specify **BSON string** in the contract. What must be avoided is letting each service pick its own representation independently.

### Watch Out for JSON APIs and Message Queues

An API may transmit a UUID as a string:

~~~json
{
  "sessionId": "00112233-4455-6677-8899-aabbccddeeff"
}
~~~

This is convenient for inter-service messaging, yet when writing to MongoDB, the adapter must **convert the string into a standard UUID/Binary** if the BSON schema requires subtype 4.

Similarly, fetching a document from MongoDB and serializing it to JSON does not guarantee fields keep their BSON types. Parsing that JSON back and inserting it into another collection can turn the field into a plain string if the proper conversion step is missing.

## 10. Handling Legacy UUID Data in a Controlled Manner

Suppose a system has many documents storing subtype 3 UUIDs and wants to migrate them to subtype 4. Migrating accurately requires knowing **which representation produced the original data**.

### Step 1: Audit the Existing Data

Identify:

- Which collections and fields contain UUIDs.
- Whether UUIDs are currently **string**, **Binary subtype 3**, **Binary subtype 4**, or mixed.
- Which drivers wrote the data, along with their versions and UUID representation settings at that time.
- Whether the UUID field serves as **`_id`**, a shard key, a logical key, a unique index field, or a foreign reference in other collections.
- Whether any service is still writing legacy formats during migration.

Inspect sample documents using canonical Extended JSON:

~~~javascript
const sample = db.sessions.findOne();

print(
  EJSON.stringify(sample, null, 2, { relaxed: false })
);
~~~

To interpret Binary subtype 3, **never rely solely on the Base64 text**; you must verify the byte order of the source data.

### Step 2: Confirm the Convention Against Known Values

Pick several documents whose original UUID strings are known from logs or upstream producers. Compare:

~~~text
Confirmed original UUID:
  00112233-4455-6677-8899-aabbccddeeff

Binary in MongoDB:
  subtype = 03
  payload = 77 66 55 44 33 22 11 00 ff ee dd cc bb aa 99 88

Interpreted as JAVA_LEGACY:
  00112233-4455-6677-8899-aabbccddeeff
~~~

This gives firm evidence that the data follows JAVA_LEGACY. If the same collection holds records written by multiple legacy drivers, a single global representation may not fit the whole collection; classify records by source or cohort.

### Step 3: Decode to Logical UUID, Then Re-Encode

A proper conversion follows three clear steps:

~~~text
BSON Binary legacy subtype 3
        |
        | Decode with original representation
        v
Logical UUID (128-bit)
        |
        | Encode with STANDARD
        v
BSON Binary standard subtype 4
~~~

Python example demonstrating an **in-memory** conversion for data verified to be JAVA_LEGACY:

~~~python
from bson.binary import Binary, UuidRepresentation

def java_legacy_to_standard(value: Binary) -> Binary:
    uuid_value = value.as_uuid(
        uuid_representation=UuidRepresentation.JAVA_LEGACY
    )
    return Binary.from_uuid(
        uuid_value,
        uuid_representation=UuidRepresentation.STANDARD
    )
~~~

This snippet does not scan an entire collection on its own, nor does it handle strings or UUIDs from other representations. Apply it only when the source data is confirmed to be JAVA_LEGACY.

**Never convert subtype 03 to 04 by flipping a single metadata byte across all documents.** For JAVA_LEGACY and CSHARP_LEGACY, the 16 bytes must also be reordered to standard byte order.

### Step 4: Plan the Data Migration

When migrating live data:

1. Back up and test the migration in a recoverable staging environment; verify that logical UUIDs match before and after.
2. Standardize new write paths on STANDARD so no further legacy values are created.
3. Migrate in controlled batches and log verification mappings between source UUID, old payload, and new payload.
4. Update related references, query filters, indexes, and downstream consumers in coordination.
5. Remove legacy read fallbacks only after no legacy data or legacy clients remain.

If the UUID is **`_id`**, you cannot simply run **`$set: { _id: ... }`** because `_id` is immutable under regular updates. That case typically requires inserting new documents with standard `_id` values, updating references, and executing a coordinated cutover.

If the UUID is a **shard key**, changing its representation also impacts chunk distribution, query routing, and shard key update rules; never perform it with a naive byte-rewriting script.

### Step 5: Verify Cross-Service Compatibility

After migration, ensure every service:

- Writes new UUIDs with subtype 4 and standard byte order.
- Reads stored BSON values using the same convention.
- Builds search filters with the same BSON representation.
- Does not downgrade UUIDs into strings when passing through JSON adapters unless the storage schema explicitly specifies strings.
- Preserves logical UUID equality across Java, Python, Node.js, and .NET.

A cross-driver integration test can use **a shared known UUID**: Service A writes it, Service B reads and queries by that UUID, and then roles are reversed. Verification should inspect **both subtype and byte payload**, not just the printed UUID string.

## 11. UUIDs, Indexes, and Query Predicates

Suppose a collection stores:

~~~javascript
db.sessions.insertOne({
  sessionId: UUID("00112233-4455-6677-8899-aabbccddeeff"),
  status: "ACTIVE"
});
~~~

Create an index:

~~~javascript
db.sessions.createIndex(
  { sessionId: 1 },
  { unique: true }
);
~~~

When the field is consistently stored as a standard UUID, the application can query uniformly by value:

~~~javascript
db.sessions.findOne({
  sessionId: UUID("00112233-4455-6677-8899-aabbccddeeff")
});
~~~

If the collection already contains documents with the equivalent logical UUID stored as a string or subtype 3, that query may miss them. Nor can a unique index automatically recognize that a string, a subtype 3 UUID, and a subtype 4 UUID represent the same business identifier.

### Do Not Confuse BSON Types with Application Logic

The following three are distinct values at the BSON layer:

~~~text
"00112233-4455-6677-8899-aabbccddeeff"     (string)

Binary subtype 03 + 16 legacy bytes         (binData)

Binary subtype 04 + 16 standard bytes       (binData)
~~~

An application may treat them as the same UUID after decoding and normalizing, yet MongoDB does not apply that business normalization automatically during equality queries.

### Choosing UUID as `_id`

When using UUID as the primary identifier, also evaluate:

- Ability to generate IDs client-side prior to insertion.
- Key distribution when concurrent writers insert records.
- Impact of UUID version (e.g., random vs. time-ordered) on index locality.
- Consistent subtype/byte conventions across all clients—a prerequisite for `_id` lookups.
- Compatibility with APIs, logs, events, and external systems.

UUID subtype 4 specifies byte storage; it **does not inherently guarantee** sort order, insert performance, or safety of your ID generation strategy.

## 12. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| UUID is an independent BSON type like string | A standard BSON UUID is **Binary subtype 4** |
| Binary is only for storing files | Binary also stores UUIDs, protocol payloads, raw bytes, and specialized subtypes |
| Two identical UUID strings always match in MongoDB | Matching depends on BSON type, subtype, and byte payload |
| Legacy UUIDs all share the same byte order | JAVA_LEGACY, CSHARP_LEGACY, and PYTHON_LEGACY use different conventions |
| Subtype 3 proves the data came from Java | Subtype 3 alone does not identify the source driver or endianness |
| STANDARD and PYTHON_LEGACY are completely identical | Their byte payloads match, yet their subtypes are 4 and 3 respectively |
| All subtype 3 records can be converted to 4 by editing the subtype | You must decode with the original representation and re-encode as STANDARD |
| Base64 in Extended JSON means MongoDB stores a Base64 string | Base64 is only for representing bytes in JSON; BSON Binary stores raw bytes |
| UUID and ObjectId share the same structure | ObjectId is a separate 12-byte BSON type; standard UUID is 16-byte Binary subtype 4 |
| Current drivers default to the same behavior as older drivers | Defaults and config APIs vary by driver and version; verify explicitly |
| `$type: "binData"` matches only standard UUIDs | It matches all Binary subtypes |
| Unpredictable UUIDs are enough for authorization | UUIDs are identifiers, not a replacement for access control checks |

## 13. Practice: Observing Standard and Legacy UUIDs

The exercises below use one consistent sample UUID:

~~~text
00112233-4455-6677-8899-aabbccddeeff
~~~

### Exercise A: Store a Standard UUID with mongosh

~~~javascript
use uuid_demo

const sessionId = UUID("00112233-4455-6677-8899-aabbccddeeff");

db.sessions.insertOne({
  _id: sessionId,
  userId: "user-101",
  createdAt: new Date()
});

db.sessions.findOne({ _id: sessionId });
~~~

Determine:

1. Which BSON type does the **`_id`** field have?
2. Which subtype does standard UUID use?
3. How many bytes are in the identifier payload?
4. If you query with a UUID string, does MongoDB automatically convert the string to Binary subtype 4?

### Exercise B: Inspect Extended JSON

~~~javascript
const document = db.sessions.findOne({
  _id: UUID("00112233-4455-6677-8899-aabbccddeeff")
});

print(EJSON.stringify(document, null, 2, { relaxed: false }));
~~~

Inspect **`$binary`**, **`base64`**, and **`subType`**. Explain why **`base64`** in JSON does not alter the stored BSON type.

### Exercise C: Compare Representations in Python

~~~python
from uuid import UUID
from bson.binary import Binary, UuidRepresentation

value = UUID("00112233-4455-6677-8899-aabbccddeeff")

for name, representation in [
    ("STANDARD", UuidRepresentation.STANDARD),
    ("PYTHON_LEGACY", UuidRepresentation.PYTHON_LEGACY),
    ("JAVA_LEGACY", UuidRepresentation.JAVA_LEGACY),
    ("CSHARP_LEGACY", UuidRepresentation.CSHARP_LEGACY),
]:
    binary = Binary.from_uuid(
        value,
        uuid_representation=representation
    )

    print(name, "subtype=", binary.subtype)
    print("bytes=", bytes(binary).hex())
    print(
        "decoded=",
        binary.as_uuid(uuid_representation=representation)
    )
~~~

This exercise lets you observe that **STANDARD** and **PYTHON_LEGACY** share the same byte order but differ in subtype, while **JAVA_LEGACY** and **CSHARP_LEGACY** also differ in byte order.

### Exercise D: Questions for a Multi-Driver System

A system has three services:

~~~text
Java service:     writes UUID to MongoDB
Python service:   reads and queries UUID from MongoDB
Node.js service:  receives UUID as JSON string from HTTP API
~~~

Specify the conventions that must be aligned at the three boundaries:

1. Which representation does Java use to convert **`java.util.UUID`** to BSON Binary?
2. Which codec setting does Python need to read and query by UUID?
3. When Node.js receives an HTTP string, what type must it convert to before writing or querying BSON?
4. When migrating subtype 3 data, why must you know the source driver?
5. If UUID resides in **`_id`**, why can't you change the subtype using a normal update?

If you can answer these, you have grasped the core takeaway: **UUID is a logical identifier; MongoDB stores it under a concrete BSON Binary representation. Cross-driver compatibility depends on both the subtype and the 16-byte ordering, not merely the UUID string developers see.**

## References

- [MongoDB Manual — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/)
- [MongoDB Manual — Extended JSON](https://www.mongodb.com/docs/manual/reference/mongodb-extended-json/)
- [MongoDB Java Sync Driver — Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [PyMongo — Documentation](https://pymongo.readthedocs.io/en/stable/)
